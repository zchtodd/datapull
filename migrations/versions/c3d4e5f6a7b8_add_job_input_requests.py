"""add job_input_requests (runtime input channel)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'job_input_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_run_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['job_run_id'], ['job_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('job_input_requests', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_job_input_requests_job_run_id'),
            ['job_run_id'], unique=False)


def downgrade():
    with op.batch_alter_table('job_input_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_input_requests_job_run_id'))
    op.drop_table('job_input_requests')
