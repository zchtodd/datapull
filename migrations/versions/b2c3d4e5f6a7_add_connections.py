"""add connections + connection_parameters, job_definitions.mfa_connection_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_connections_name'), ['name'], unique=True)

    op.create_table(
        'connection_parameters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('value_type', sa.String(length=16), nullable=False, server_default='string'),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('connection_id', 'key', name='uq_connection_parameter_key'),
    )
    with op.batch_alter_table('connection_parameters', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_connection_parameters_connection_id'),
            ['connection_id'], unique=False)

    with op.batch_alter_table('job_definitions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mfa_connection_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_job_definitions_mfa_connection_id', 'connections',
            ['mfa_connection_id'], ['id'])


def downgrade():
    with op.batch_alter_table('job_definitions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_job_definitions_mfa_connection_id', type_='foreignkey')
        batch_op.drop_column('mfa_connection_id')

    with op.batch_alter_table('connection_parameters', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_connection_parameters_connection_id'))
    op.drop_table('connection_parameters')

    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_connections_name'))
    op.drop_table('connections')
