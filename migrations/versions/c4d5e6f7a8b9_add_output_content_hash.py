"""add content_hash + is_new to job_run_outputs

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-23

"""
import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_run_outputs", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("job_run_outputs", sa.Column("is_new", sa.Boolean(), nullable=True))
    op.create_index(
        "ix_job_run_outputs_content_hash", "job_run_outputs", ["content_hash"]
    )


def downgrade():
    op.drop_index("ix_job_run_outputs_content_hash", table_name="job_run_outputs")
    op.drop_column("job_run_outputs", "is_new")
    op.drop_column("job_run_outputs", "content_hash")
