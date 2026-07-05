"""connection role bindings: drop job_definitions.mfa_connection_id,
add job_definition_connections + job_run_connections

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('job_definitions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_job_definitions_mfa_connection_id', type_='foreignkey')
        batch_op.drop_column('mfa_connection_id')

    op.create_table(
        'job_definition_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_definition_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['job_definition_id'], ['job_definitions.id'], ),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_definition_id', 'role', name='uq_jobdef_conn_role'),
    )
    with op.batch_alter_table('job_definition_connections', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_job_definition_connections_job_definition_id'),
            ['job_definition_id'], unique=False)

    op.create_table(
        'job_run_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_run_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['job_run_id'], ['job_runs.id'], ),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('job_run_connections', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_job_run_connections_job_run_id'),
            ['job_run_id'], unique=False)


def downgrade():
    with op.batch_alter_table('job_run_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_run_connections_job_run_id'))
    op.drop_table('job_run_connections')
    with op.batch_alter_table('job_definition_connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_definition_connections_job_definition_id'))
    op.drop_table('job_definition_connections')
    with op.batch_alter_table('job_definitions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mfa_connection_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_job_definitions_mfa_connection_id', 'connections',
            ['mfa_connection_id'], ['id'])
