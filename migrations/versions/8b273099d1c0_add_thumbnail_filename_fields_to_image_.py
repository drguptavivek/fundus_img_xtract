"""Add thumbnail filename fields to image models

Revision ID: 8b273099d1c0
Revises: cd23f993eaf2
Create Date: 2025-11-11 04:10:35.949333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b273099d1c0'
down_revision: Union[str, Sequence[str], None] = 'cd23f993eaf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add thumbnail fields to DirectImageUpload
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    diu_columns = {column["name"] for column in inspector.get_columns("direct_image_uploads")}
    ef_columns = {column["name"] for column in inspector.get_columns("encounter_files")}

    if "thumbnail_filename" not in diu_columns:
        op.add_column('direct_image_uploads', sa.Column('thumbnail_filename', sa.String(length=255), nullable=True))
    if "edited_thumbnail_filename" not in diu_columns:
        op.add_column('direct_image_uploads', sa.Column('edited_thumbnail_filename', sa.String(length=255), nullable=True))

    # Add thumbnail field to EncounterFile
    if "thumbnail_filename" not in ef_columns:
        op.add_column('encounter_files', sa.Column('thumbnail_filename', sa.String(length=255), nullable=True))

    # Add check constraints for DirectImageUpload thumbnail fields
    diu_checks = {check["name"] for check in inspector.get_check_constraints("direct_image_uploads")}
    if "ck_diu_thumbnail_filename_no_slash" not in diu_checks:
        op.create_check_constraint(
            'ck_diu_thumbnail_filename_no_slash',
            'direct_image_uploads',
            "thumbnail_filename IS NULL OR position('/' in thumbnail_filename) = 0"
        )
    if "ck_diu_edited_thumbnail_filename_no_slash" not in diu_checks:
        op.create_check_constraint(
            'ck_diu_edited_thumbnail_filename_no_slash',
            'direct_image_uploads',
            "edited_thumbnail_filename IS NULL OR position('/' in edited_thumbnail_filename) = 0"
        )

    # Add check constraint for EncounterFile thumbnail field
    ef_checks = {check["name"] for check in inspector.get_check_constraints("encounter_files")}
    if "ck_ef_thumbnail_filename_no_slash" not in ef_checks:
        op.create_check_constraint(
            'ck_ef_thumbnail_filename_no_slash',
            'encounter_files',
            "thumbnail_filename IS NULL OR position('/' in thumbnail_filename) = 0"
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop check constraints in reverse order
    op.drop_constraint('ck_ef_thumbnail_filename_no_slash', 'encounter_files', type_='check')
    op.drop_constraint('ck_diu_edited_thumbnail_filename_no_slash', 'direct_image_uploads', type_='check')
    op.drop_constraint('ck_diu_thumbnail_filename_no_slash', 'direct_image_uploads', type_='check')

    # Drop columns in reverse order
    op.drop_column('encounter_files', 'thumbnail_filename')
    op.drop_column('direct_image_uploads', 'edited_thumbnail_filename')
    op.drop_column('direct_image_uploads', 'thumbnail_filename')
