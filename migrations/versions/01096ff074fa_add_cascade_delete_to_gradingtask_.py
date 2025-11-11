"""Add cascade delete to GradingTask foreign keys

Revision ID: 01096ff074fa
Revises: 8b273099d1c0
Create Date: 2025-11-11 16:00:59.088441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01096ff074fa'
down_revision: Union[str, Sequence[str], None] = '8b273099d1c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop existing foreign key constraints
    op.drop_constraint('grading_tasks_direct_image_upload_id_fkey', 'grading_tasks', type_='foreignkey')
    op.drop_constraint('grading_tasks_encounter_file_id_fkey', 'grading_tasks', type_='foreignkey')

    # Re-add foreign key constraints with CASCADE delete
    op.create_foreign_key(
        'grading_tasks_direct_image_upload_id_fkey', 'grading_tasks', 'direct_image_uploads',
        ['direct_image_upload_id'], ['id'], ondelete='CASCADE'
    )
    op.create_foreign_key(
        'grading_tasks_encounter_file_id_fkey', 'grading_tasks', 'encounter_files',
        ['encounter_file_id'], ['id'], ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key constraints with CASCADE delete
    op.drop_constraint('grading_tasks_direct_image_upload_id_fkey', 'grading_tasks', type_='foreignkey')
    op.drop_constraint('grading_tasks_encounter_file_id_fkey', 'grading_tasks', type_='foreignkey')

    # Re-add foreign key constraints without CASCADE delete
    op.create_foreign_key(
        'grading_tasks_direct_image_upload_id_fkey', 'grading_tasks', 'direct_image_uploads',
        ['direct_image_upload_id'], ['id']
    )
    op.create_foreign_key(
        'grading_tasks_encounter_file_id_fkey', 'grading_tasks', 'encounter_files',
        ['encounter_file_id'], ['id']
    )
