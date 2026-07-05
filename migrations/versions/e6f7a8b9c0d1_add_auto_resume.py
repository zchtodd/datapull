"""add auto-resume fields to job_runs and job_definitions

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-30

"""
import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_runs", sa.Column("exit_code", sa.Integer(), nullable=True))
    op.add_column(
        "job_runs",
        sa.Column("auto_resume_attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("job_runs", sa.Column("auto_resume_at", sa.DateTime(), nullable=True))
    op.add_column(
        "job_definitions",
        sa.Column("auto_resume_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "job_definitions",
        sa.Column("auto_resume_max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade():
    op.drop_column("job_definitions", "auto_resume_max_attempts")
    op.drop_column("job_definitions", "auto_resume_enabled")
    op.drop_column("job_runs", "auto_resume_at")
    op.drop_column("job_runs", "auto_resume_attempt")
    op.drop_column("job_runs", "exit_code")
