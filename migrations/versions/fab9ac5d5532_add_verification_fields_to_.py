"""Add verification fields to EncounterSetImage (anonymized, reviewed, not_gradable)

Revision ID: fab9ac5d5532
Revises: fc94d51475fd
Create Date: 2026-01-31 09:42:39.957107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fab9ac5d5532'
down_revision: Union[str, Sequence[str], None] = 'fc94d51475fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add verification fields to EncounterSetImage."""
    # Get database connection
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if columns exist before adding (idempotent)
    existing_columns = [c['name'] for c in inspector.get_columns('encounter_set_images')]

    # Add is_anonymized column
    if 'is_anonymized' not in existing_columns:
        op.add_column('encounter_set_images',
                     sa.Column('is_anonymized', sa.Boolean(), nullable=False, server_default='false'))

    # Add is_reviewed column
    if 'is_reviewed' not in existing_columns:
        op.add_column('encounter_set_images',
                     sa.Column('is_reviewed', sa.Boolean(), nullable=False, server_default='false'))

    # Add is_not_gradable column
    if 'is_not_gradable' not in existing_columns:
        op.add_column('encounter_set_images',
                     sa.Column('is_not_gradable', sa.Boolean(), nullable=False, server_default='false'))

    # Add not_gradable_reason column
    if 'not_gradable_reason' not in existing_columns:
        op.add_column('encounter_set_images',
                     sa.Column('not_gradable_reason', sa.String(length=512), nullable=True))


def downgrade() -> None:
    """Downgrade schema - remove verification fields from EncounterSetImage."""
    # Get database connection
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if columns exist before dropping (idempotent)
    existing_columns = [c['name'] for c in inspector.get_columns('encounter_set_images')]

    if 'not_gradable_reason' in existing_columns:
        op.drop_column('encounter_set_images', 'not_gradable_reason')

    if 'is_not_gradable' in existing_columns:
        op.drop_column('encounter_set_images', 'is_not_gradable')

    if 'is_reviewed' in existing_columns:
        op.drop_column('encounter_set_images', 'is_reviewed')

    if 'is_anonymized' in existing_columns:
        op.drop_column('encounter_set_images', 'is_anonymized')
