from flask import flash, redirect, render_template, request, url_for
from flask.views import MethodView
from flask_login import current_user, login_user

from app.extensions import db
from app.models import User


def _is_safe_next(target: str | None) -> bool:
    """Only allow relative redirects, to avoid open-redirect attacks."""
    return bool(target) and target.startswith("/") and not target.startswith("//")


class LoginView(MethodView):
    def get(self):
        if current_user.is_authenticated:
            return redirect(url_for("main.index"))
        return render_template("login.html")

    def post(self):
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(User).filter_by(email=email))
        if user and user.is_active and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next")
            return redirect(
                next_url if _is_safe_next(next_url) else url_for("main.index")
            )
        flash("Invalid email or password.", "error")
        return render_template("login.html")
