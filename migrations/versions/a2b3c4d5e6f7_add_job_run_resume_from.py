"""add job run resume_from_run_id

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-22

"""
import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_runs", sa.Column("resume_from_run_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_job_runs_resume_from_run_id", "job_runs", ["resume_from_run_id"]
    )
    # SQLite can't ALTER TABLE ADD a foreign key (and doesn't enforce FKs by
    # default), so the column + index are sufficient there. Add the real FK on
    # engines that support it (e.g. SQL Server).
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_job_runs_resume_from_run_id", "job_runs", "job_runs",
            ["resume_from_run_id"], ["id"],
        )


def downgrade():
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "fk_job_runs_resume_from_run_id", "job_runs", type_="foreignkey")
    op.drop_index("ix_job_runs_resume_from_run_id", table_name="job_runs")
    op.drop_column("job_runs", "resume_from_run_id")
