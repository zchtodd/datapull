"""add job_runs.runtime_token_hash (per-run runtime API token)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('runtime_token_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_job_runs_runtime_token_hash'),
            ['runtime_token_hash'], unique=False)


def downgrade():
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_runs_runtime_token_hash'))
        batch_op.drop_column('runtime_token_hash')
