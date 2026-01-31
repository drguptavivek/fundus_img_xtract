"""Add S3 sync status tracking and S3 fields to EncounterSetImage

Revision ID: 198d644ccbce
Revises: 5fdee7f56f61
Create Date: 2026-01-31 17:51:47.464190

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '198d644ccbce'
down_revision: Union[str, Sequence[str], None] = '5fdee7f56f61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create s3_sync_status table
    op.create_table(
        's3_sync_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('s3_config_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('variant', sa.String(length=50), nullable=False, server_default='original'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'success', 'failed')",
            name='ck_s3_sync_status'
        ),
        sa.CheckConstraint(
            "variant IN ('original', 'thumbnail', 'edited', 'edited_thumbnail')",
            name='ck_s3_sync_variant'
        ),
        sa.ForeignKeyConstraint(['s3_config_id'], ['s3_configs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_type', 'file_id', 'variant', name='uq_s3_sync_file_variant')
    )
    # Create indexes for s3_sync_status
    op.create_index('ix_s3_sync_status_file_type', 's3_sync_status', ['file_type'], unique=False)
    op.create_index('ix_s3_sync_status_file_id', 's3_sync_status', ['file_id'], unique=False)
    op.create_index('ix_s3_sync_status_status', 's3_sync_status', ['status'], unique=False)
    op.create_index('ix_s3_sync_status_s3_config_id', 's3_sync_status', ['s3_config_id'], unique=False)
    op.create_index('ix_s3_sync_status_config', 's3_sync_status', ['s3_config_id', 'status'], unique=False)
    op.create_index('ix_s3_sync_status_created', 's3_sync_status', ['s3_config_id', 'status', 'created_at'], unique=False)
    op.create_index('ix_s3_sync_file_type_id', 's3_sync_status', ['file_type', 'file_id'], unique=False)

    # Add S3 fields to encounter_set_images (if not already exists)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('encounter_set_images')]

    if 'hospital_id' not in columns:
        op.add_column('encounter_set_images', sa.Column('hospital_id', sa.Integer(), nullable=True))
        op.create_foreign_key(None, 'encounter_set_images', 'hospitals', ['hospital_id'], ['id'])
        op.create_index('ix_esi_hospital_id', 'encounter_set_images', ['hospital_id'], unique=False)

    if 's3_config_id' not in columns:
        op.add_column('encounter_set_images', sa.Column('s3_config_id', sa.Integer(), nullable=True))
        op.create_foreign_key(None, 'encounter_set_images', 's3_configs', ['s3_config_id'], ['id'])
        op.create_index('ix_esi_s3_config_uuid', 'encounter_set_images', ['s3_config_id', 'uuid'], unique=False)

    if 's3_object_key' not in columns:
        op.add_column('encounter_set_images', sa.Column('s3_object_key', sa.String(length=500), nullable=True))

    if 's3_object_key_edited' not in columns:
        op.add_column('encounter_set_images', sa.Column('s3_object_key_edited', sa.String(length=500), nullable=True))

    if 's3_object_key_thumbnail' not in columns:
        op.add_column('encounter_set_images', sa.Column('s3_object_key_thumbnail', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop S3 fields from encounter_set_images
    op.drop_column('encounter_set_images', 's3_object_key_thumbnail')
    op.drop_column('encounter_set_images', 's3_object_key_edited')
    op.drop_column('encounter_set_images', 's3_object_key')

    # Drop indexes and foreign keys
    op.drop_index('ix_esi_s3_config_uuid', table_name='encounter_set_images')
    op.drop_index('ix_esi_hospital_id', table_name='encounter_set_images')

    # Need to drop constraints manually
    conn = op.get_bind()
    conn.execute(sa.text("""
        ALTER TABLE encounter_set_images
        DROP CONSTRAINT IF EXISTS encounter_set_images_s3_config_id_fkey
    """))
    conn.execute(sa.text("""
        ALTER TABLE encounter_set_images
        DROP CONSTRAINT IF EXISTS encounter_set_images_hospital_id_fkey
    """))

    op.drop_column('encounter_set_images', 's3_config_id')
    op.drop_column('encounter_set_images', 'hospital_id')

    # Drop s3_sync_status table
    op.drop_index('ix_s3_sync_file_type_id', table_name='s3_sync_status')
    op.drop_index('ix_s3_sync_status_created', table_name='s3_sync_status')
    op.drop_index('ix_s3_sync_status_config', table_name='s3_sync_status')
    op.drop_index('ix_s3_sync_status_s3_config_id', table_name='s3_sync_status')
    op.drop_index('ix_s3_sync_status_status', table_name='s3_sync_status')
    op.drop_index('ix_s3_sync_status_file_id', table_name='s3_sync_status')
    op.drop_index('ix_s3_sync_status_file_type', table_name='s3_sync_status')
    op.drop_table('s3_sync_status')
