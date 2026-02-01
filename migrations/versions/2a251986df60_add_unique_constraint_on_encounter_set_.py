"""Add unique constraint on encounter_set_image position

Revision ID: 2a251986df60
Revises: 198d644ccbce
Create Date: 2026-02-01 04:09:15.469052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2a251986df60'
down_revision: Union[str, Sequence[str], None] = '198d644ccbce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add unique constraint on encounter_set_image position"""
    from sqlalchemy.engine.reflection import Inspector

    # Add unique constraint on encounter_set_images (idempotent)
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # Check if constraint already exists (idempotent - safe to re-run)
    constraints = [c['name'] for c in inspector.get_unique_constraints('encounter_set_images')]
    if 'uq_encounter_set_image_position' not in constraints:
        op.create_unique_constraint(
            'uq_encounter_set_image_position',
            'encounter_set_images',
            ['patient_encounter_id', 'spatial_position']
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema - Remove unique constraint on encounter_set_image position"""
    from sqlalchemy.engine.reflection import Inspector

    # Remove unique constraint on encounter_set_images (idempotent)
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    constraints = [c['name'] for c in inspector.get_unique_constraints('encounter_set_images')]
    if 'uq_encounter_set_image_position' in constraints:
        op.drop_constraint('uq_encounter_set_image_position', 'encounter_set_images', type_='unique')
    # ### end Alembic commands ###
