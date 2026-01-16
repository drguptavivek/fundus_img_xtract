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
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'image_gradings')
               AND NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'image_gradings_archive') THEN
                CREATE TABLE image_gradings_archive AS
                SELECT * FROM image_gradings;
            END IF;
        END $$;
    """)

    # Log the archival for audit purposes
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'image_gradings_archive') THEN
                COMMENT ON TABLE image_gradings_archive IS 'Archive of legacy ImageGrading data before migration to Grade model. Created on 2025-11-09';
            END IF;
        END $$;
    """)

    # Drop the image_gradings table
    op.execute("DROP TABLE IF EXISTS image_gradings")

    # Note: The ImageGrading model class should be removed from models.py after this migration


def downgrade() -> None:
    """Downgrade schema - Recreate ImageGrading table from archive."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # Recreate the image_gradings table
    if "image_gradings" not in existing_tables:
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
        existing_tables.add("image_gradings")

    # Create indexes
    if existing_tables and "image_gradings" in existing_tables:
        if not op.get_context().dialect.has_index(conn, "image_gradings", op.f('ix_image_gradings_encounter_file_id')):
            op.create_index(op.f('ix_image_gradings_encounter_file_id'), 'image_gradings', ['encounter_file_id'], unique=False)
        if not op.get_context().dialect.has_index(conn, "image_gradings", op.f('ix_image_gradings_direct_image_upload_id')):
            op.create_index(op.f('ix_image_gradings_direct_image_upload_id'), 'image_gradings', ['direct_image_upload_id'], unique=False)
        if not op.get_context().dialect.has_index(conn, "image_gradings", op.f('ix_image_gradings_grader_user_id')):
            op.create_index(op.f('ix_image_gradings_grader_user_id'), 'image_gradings', ['grader_user_id'], unique=False)
        if not op.get_context().dialect.has_index(conn, "image_gradings", op.f('ix_image_gradings_grader_role')):
            op.create_index(op.f('ix_image_gradings_grader_role'), 'image_gradings', ['grader_role'], unique=False)
        if not op.get_context().dialect.has_index(conn, "image_gradings", op.f('ix_image_gradings_graded_for')):
            op.create_index(op.f('ix_image_gradings_graded_for'), 'image_gradings', ['graded_for'], unique=False)

    # Create composite indexes
    if existing_tables and "image_gradings" in existing_tables:
        if not op.get_context().dialect.has_index(conn, "image_gradings", 'ix_image_gradings_image_user_role_for'):
            op.create_index('ix_image_gradings_image_user_role_for', 'image_gradings',
                           ['encounter_file_id', 'grader_user_id', 'grader_role', 'graded_for'], unique=False)
        if not op.get_context().dialect.has_index(conn, "image_gradings", 'ix_image_gradings_direct_user_role_for'):
            op.create_index('ix_image_gradings_direct_user_role_for', 'image_gradings',
                           ['direct_image_upload_id', 'grader_user_id', 'grader_role', 'graded_for'], unique=False)

    # Restore data from archive if it exists
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'image_gradings_archive')
               AND EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'image_gradings') THEN
                INSERT INTO image_gradings
                SELECT * FROM image_gradings_archive;
            END IF;
        END $$;
    """)

    # Drop the archive table after successful restore
    op.execute("DROP TABLE IF EXISTS image_gradings_archive")
