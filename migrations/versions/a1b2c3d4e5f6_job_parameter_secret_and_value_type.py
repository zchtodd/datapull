"""job_parameter: add is_secret + value_type, widen value to Text

Existing rows were all encrypted under the old EncryptedString column, so they
are backfilled as is_secret=True to keep decrypting correctly.

Revision ID: a1b2c3d4e5f6
Revises: de55607a45da
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'de55607a45da'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('job_parameters', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_secret', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column('value_type', sa.String(length=16), nullable=False,
                      server_default='string')
        )
        # Widen value from VARCHAR(1024) to Text (NVARCHAR(MAX) on SQL Server).
        batch_op.alter_column('value', existing_type=sa.String(length=1024),
                              type_=sa.Text(), existing_nullable=True)

    # Pre-existing parameter values were stored encrypted, so mark them secret.
    op.execute("UPDATE job_parameters SET is_secret = 1")


def downgrade():
    # Truncate any values too long for the narrower column before shrinking.
    op.execute("UPDATE job_parameters SET value = LEFT(value, 1024) "
               "WHERE value IS NOT NULL AND LEN(value) > 1024")
    with op.batch_alter_table('job_parameters', schema=None) as batch_op:
        batch_op.alter_column('value', existing_type=sa.Text(),
                              type_=sa.String(length=1024), existing_nullable=True)
        batch_op.drop_column('value_type')
        batch_op.drop_column('is_secret')
