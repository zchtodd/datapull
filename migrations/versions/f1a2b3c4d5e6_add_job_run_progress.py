"""add job run progress tracking

Revision ID: f1a2b3c4d5e6
Revises: c9d0e1f2a3b4
Create Date: 2026-06-22

"""
import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_runs", sa.Column("progress_total", sa.Integer(), nullable=True))
    op.add_column(
        "job_runs",
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("job_runs", sa.Column("progress_message", sa.String(length=255), nullable=True))
    op.add_column("job_runs", sa.Column("progress_updated_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("job_runs", "progress_updated_at")
    op.drop_column("job_runs", "progress_message")
    op.drop_column("job_runs", "progress_current")
    op.drop_column("job_runs", "progress_total")
