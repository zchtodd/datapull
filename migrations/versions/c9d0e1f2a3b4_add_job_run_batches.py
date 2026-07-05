"""add job_run_batches + job_runs.batch_id/client_label + connections.is_shared

Backfills a batch per existing run so dashboard history isn't lost.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'job_run_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_definition_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_definition_id'], ['job_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('job_run_batches', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_job_run_batches_job_definition_id'),
            ['job_definition_id'], unique=False)

    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('batch_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('client_label', sa.String(length=255), nullable=True))
        batch_op.create_index(batch_op.f('ix_job_runs_batch_id'), ['batch_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_job_runs_batch_id', 'job_run_batches', ['batch_id'], ['id'])

    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_shared', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))

    # Backfill: wrap each existing run in its own batch (batch-of-1).
    op.execute(
        "INSERT INTO job_run_batches (job_definition_id, created_at) "
        "SELECT job_definition_id, created_at FROM job_runs"
    )
    # Match each run to the batch row created from it (same def + created_at).
    op.execute(
        "UPDATE jr SET batch_id = b.id "
        "FROM job_runs jr "
        "JOIN job_run_batches b "
        "  ON ((b.job_definition_id = jr.job_definition_id) "
        "      OR (b.job_definition_id IS NULL AND jr.job_definition_id IS NULL)) "
        "  AND b.created_at = jr.created_at "
        "WHERE jr.batch_id IS NULL"
    )


def downgrade():
    with op.batch_alter_table('connections', schema=None) as batch_op:
        batch_op.drop_column('is_shared')
    with op.batch_alter_table('job_runs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_job_runs_batch_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_job_runs_batch_id'))
        batch_op.drop_column('client_label')
        batch_op.drop_column('batch_id')
    with op.batch_alter_table('job_run_batches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_run_batches_job_definition_id'))
    op.drop_table('job_run_batches')
