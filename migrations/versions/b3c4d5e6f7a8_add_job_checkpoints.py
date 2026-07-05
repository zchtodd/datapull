"""add job_checkpoints table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-06-23

"""
import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_checkpoints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_definition_id", sa.Integer(), nullable=False),
        sa.Column("namespace", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DONE"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_definition_id"], ["job_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_checkpoints_def_ns", "job_checkpoints",
        ["job_definition_id", "namespace"],
    )


def downgrade():
    op.drop_index("ix_job_checkpoints_def_ns", table_name="job_checkpoints")
    op.drop_table("job_checkpoints")
