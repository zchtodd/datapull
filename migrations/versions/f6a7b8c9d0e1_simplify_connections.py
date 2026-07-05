"""simplify connections: drop type + roles, add connections.is_mfa

Connection.type -> connections.is_mfa (graph_mailbox becomes is_mfa=true).
job_definition_connections / job_run_connections lose their `role` column
(jobs now just attach connections; an attached MFA connection drives MFA).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    # connections: add is_mfa, derive from the old type, drop type.
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_mfa', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    op.execute("UPDATE connections SET is_mfa = 1 WHERE type = 'graph_mailbox'")
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_column('type')

    # job_definition_connections: drop role + its unique key, add (job, conn) unique.
    with op.batch_alter_table('job_definition_connections', schema=None) as batch_op:
        batch_op.drop_constraint('uq_jobdef_conn_role', type_='unique')
        batch_op.drop_column('role')
        batch_op.create_unique_constraint(
            'uq_jobdef_conn', ['job_definition_id', 'connection_id'])

    # job_run_connections: drop role.
    with op.batch_alter_table('job_run_connections', schema=None) as batch_op:
        batch_op.drop_column('role')


def downgrade():
    with op.batch_alter_table('job_run_connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=32), nullable=False,
                                      server_default='account'))

    with op.batch_alter_table('job_definition_connections', schema=None) as batch_op:
        batch_op.drop_constraint('uq_jobdef_conn', type_='unique')
        batch_op.add_column(sa.Column('role', sa.String(length=32), nullable=False,
                                      server_default='account'))
        batch_op.create_unique_constraint(
            'uq_jobdef_conn_role', ['job_definition_id', 'role'])

    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('type', sa.String(length=32), nullable=False,
                                      server_default='generic'))
    op.execute("UPDATE connections SET type = 'graph_mailbox' WHERE is_mfa = 1")
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_column('is_mfa')
