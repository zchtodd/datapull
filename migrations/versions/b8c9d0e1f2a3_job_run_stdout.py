"""add job_runs.stdout (captured container output)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stdout', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.drop_column('stdout')
