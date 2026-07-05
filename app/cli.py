import os

import click
from flask import Flask

from app.extensions import db
from app.models import Role, User


def register_cli(app: Flask) -> None:
    @app.cli.command("bootstrap-admin")
    def bootstrap_admin() -> None:
        """Create or update an admin user from ADMIN_EMAIL / ADMIN_PASSWORD.

        Idempotent: safe to run repeatedly. The environment variables are the
        source of truth — the admin's password is (re)set to ADMIN_PASSWORD.
        """
        email = os.environ.get("ADMIN_EMAIL")
        password = os.environ.get("ADMIN_PASSWORD")
        if not email or not password:
            raise click.ClickException(
                "ADMIN_EMAIL and ADMIN_PASSWORD must both be set."
            )

        user = db.session.scalar(db.select(User).filter_by(email=email))
        created = user is None
        if user is None:
            user = User(email=email)
            db.session.add(user)
        user.role = Role.ADMIN
        user.is_active = True
        user.set_password(password)
        db.session.commit()
        click.echo(f"{'Created' if created else 'Updated'} admin {email}")

    @app.cli.command("create-user")
    @click.argument("email")
    @click.password_option()
    @click.option("--admin", is_flag=True, help="Grant the admin role.")
    def create_user(email: str, password: str, admin: bool) -> None:
        """Create a user (use --admin for an admin account)."""
        if db.session.scalar(db.select(User).filter_by(email=email)):
            raise click.ClickException(f"User {email} already exists.")
        user = User(email=email, role=Role.ADMIN if admin else Role.USER)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {user!r}")
