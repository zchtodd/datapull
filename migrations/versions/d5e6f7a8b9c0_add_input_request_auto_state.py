"""add automated-retrieval state to job_input_requests

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-29

"""
import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job_input_requests",
        sa.Column("auto_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "job_input_requests",
        sa.Column("auto_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "job_input_requests",
        sa.Column("auto_failed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "job_input_requests",
        sa.Column("auto_last_error", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("job_input_requests", "auto_last_error")
    op.drop_column("job_input_requests", "auto_failed")
    op.drop_column("job_input_requests", "auto_attempts")
    op.drop_column("job_input_requests", "auto_enabled")
