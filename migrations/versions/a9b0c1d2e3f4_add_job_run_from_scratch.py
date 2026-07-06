"""add job_runs.from_scratch

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-07-06

"""
import sqlalchemy as sa
from alembic import op

revision = "a9b0c1d2e3f4"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job_runs",
        sa.Column("from_scratch", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("job_runs", "from_scratch")
