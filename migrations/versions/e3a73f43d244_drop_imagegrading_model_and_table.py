"""Drop ImageGrading model and table

Revision ID: e3a73f43d244
Revises: add_ip_address_to_flask_sessions
Create Date: 2025-11-09 23:19:44.989100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3a73f43d244'
down_revision: Union[str, Sequence[str], None] = 'add_ip_address_to_flask_sessions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Drop ImageGrading table and related indexes."""

    # First, create a backup table of ImageGrading data for archival purposes
    # This ensures historical data is preserved before dropping the table
    op.execute("""
        CREATE TABLE image_gradings_archive AS
        SELECT * FROM image_gradings
    """)

    # Log the archival for audit purposes
    op.execute("""
        COMMENT ON TABLE image_gradings_archive IS 'Archive of legacy ImageGrading data before migration to Grade model. Created on 2025-11-09'
    """)

    # Drop the image_gradings table
    op.drop_table('image_gradings')

    # Note: The ImageGrading model class should be removed from models.py after this migration


def downgrade() -> None:
    """Downgrade schema - Recreate ImageGrading table from archive."""

    # Recreate the image_gradings table
    op.create_table(
        'image_gradings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('encounter_file_id', sa.Integer(), nullable=True),
        sa.Column('direct_image_upload_id', sa.Integer(), nullable=True),
        sa.Column('grader_user_id', sa.Integer(), nullable=True),
        sa.Column('grader_username', sa.String(length=150), nullable=True),
        sa.Column('grader_role', sa.String(length=32), nullable=True),
        sa.Column('graded_for', sa.String(length=32), nullable=False),
        sa.Column('impression', sa.String(length=32), nullable=False),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['direct_image_upload_id'], ['direct_image_uploads.id'], ),
        sa.ForeignKeyConstraint(['encounter_file_id'], ['encounter_files.id'], ),
        sa.ForeignKeyConstraint(['grader_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(op.f('ix_image_gradings_encounter_file_id'), 'image_gradings', ['encounter_file_id'], unique=False)
    op.create_index(op.f('ix_image_gradings_direct_image_upload_id'), 'image_gradings', ['direct_image_upload_id'], unique=False)
    op.create_index(op.f('ix_image_gradings_grader_user_id'), 'image_gradings', ['grader_user_id'], unique=False)
    op.create_index(op.f('ix_image_gradings_grader_role'), 'image_gradings', ['grader_role'], unique=False)
    op.create_index(op.f('ix_image_gradings_graded_for'), 'image_gradings', ['graded_for'], unique=False)

    # Create composite indexes
    op.create_index('ix_image_gradings_image_user_role_for', 'image_gradings',
                   ['encounter_file_id', 'grader_user_id', 'grader_role', 'graded_for'], unique=False)
    op.create_index('ix_image_gradings_direct_user_role_for', 'image_gradings',
                   ['direct_image_upload_id', 'grader_user_id', 'grader_role', 'graded_for'], unique=False)

    # Restore data from archive if it exists
    op.execute("""
        INSERT INTO image_gradings
        SELECT * FROM image_gradings_archive
    """)

    # Drop the archive table after successful restore
    op.drop_table('image_gradings_archive')
