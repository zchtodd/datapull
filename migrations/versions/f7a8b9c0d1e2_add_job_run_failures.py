"""add job_run_failures table

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-01

"""
import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_run_failures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_run_id", sa.Integer(), nullable=False),
        sa.Column("item", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("label", sa.String(length=512), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("evidence", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_run_failures_job_run_id", "job_run_failures", ["job_run_id"]
    )


def downgrade():
    op.drop_index("ix_job_run_failures_job_run_id", table_name="job_run_failures")
    op.drop_table("job_run_failures")
