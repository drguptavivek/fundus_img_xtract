"""Add disease_id to PatientEncounters for encounter-set disease tracking

Revision ID: 5d6f103a0019
Revises: 50d6eca5967e
Create Date: 2026-01-31 12:54:51.215103

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d6f103a0019'
down_revision: Union[str, Sequence[str], None] = '50d6eca5967e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add disease_id to PatientEncounters."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Check if column already exists (idempotent)
    existing_columns = [c['name'] for c in inspector.get_columns('patient_encounters')]

    if 'disease_id' not in existing_columns:
        # Add disease_id column with foreign key to diseases table
        op.add_column(
            'patient_encounters',
            sa.Column('disease_id', sa.Integer(), nullable=True)
        )

        # Create foreign key constraint
        op.create_foreign_key(
            'fk_patient_encounters_disease_id_diseases',
            'patient_encounters',
            'diseases',
            ['disease_id'],
            ['id']
        )

        # Create index for efficient queries
        op.create_index(
            'ix_patient_encounters_disease_id',
            'patient_encounters',
            ['disease_id']
        )


def downgrade() -> None:
    """Downgrade schema - remove disease_id from PatientEncounters."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    existing_columns = [c['name'] for c in inspector.get_columns('patient_encounters')]

    # Drop index if exists
    if 'ix_patient_encounters_disease_id' in existing_columns:
        op.drop_index('ix_patient_encounters_disease_id', table_name='patient_encounters')

    # Drop foreign key if exists
    try:
        op.drop_constraint('fk_patient_encounters_disease_id_diseases', 'patient_encounters', type_='foreignkey')
    except Exception:
        pass

    # Drop column if exists
    if 'disease_id' in existing_columns:
        op.drop_column('patient_encounters', 'disease_id')
