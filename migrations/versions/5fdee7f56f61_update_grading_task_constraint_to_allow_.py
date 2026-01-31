"""Update grading_task constraint to allow patient_encounter_id

Revision ID: 5fdee7f56f61
Revises: 5d6f103a0019
Create Date: 2026-01-31 13:23:38.381879

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fdee7f56f61'
down_revision: Union[str, Sequence[str], None] = '5d6f103a0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Update the check constraint to allow patient_encounter_id in addition to
    encounter_file_id and direct_image_upload_id.
    """
    # Drop the old constraint
    op.execute("""
        ALTER TABLE grading_tasks
        DROP CONSTRAINT IF EXISTS ck_grading_task_either_encounter_or_direct
    """)

    # Create new constraint that allows exactly one of:
    # - encounter_file_id
    # - direct_image_upload_id
    # - patient_encounter_id
    op.execute("""
        ALTER TABLE grading_tasks
        ADD CONSTRAINT ck_grading_task_one_image_ref
        CHECK (
            (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NULL) OR
            (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL AND patient_encounter_id IS NULL) OR
            (encounter_file_id IS NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NOT NULL)
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the new constraint
    op.execute("""
        ALTER TABLE grading_tasks
        DROP CONSTRAINT IF EXISTS ck_grading_task_one_image_ref
    """)

    # Restore the old constraint (without patient_encounter_id support)
    op.execute("""
        ALTER TABLE grading_tasks
        ADD CONSTRAINT ck_grading_task_either_encounter_or_direct
        CHECK (
            (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR
            (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
        )
    """)
