"""add job_definitions.last_scheduled_at (scheduler bookkeeping)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('job_definitions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_scheduled_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('job_definitions', schema=None) as batch_op:
        batch_op.drop_column('last_scheduled_at')
