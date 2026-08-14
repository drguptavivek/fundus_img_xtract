"""Add encounter set workflow schema

Revision ID: 45867a4765ec
Revises: 7f5183911935
Create Date: 2026-01-31 02:22:27.285333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '45867a4765ec'
down_revision: Union[str, Sequence[str], None] = '7f5183911935'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with idempotency checks."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Create encounter_set_images table
    if 'encounter_set_images' not in tables:
        op.create_table('encounter_set_images',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('uuid', sa.String(length=36), nullable=False),
            sa.Column('patient_encounter_id', sa.Integer(), nullable=False),
            sa.Column('spatial_position', sa.Integer(), nullable=False),
            sa.Column('original_filename', sa.String(length=255), nullable=False),
            sa.Column('edited_filename', sa.String(length=255), nullable=True),
            sa.Column('thumbnail_filename', sa.String(length=255), nullable=True),
            sa.Column('folder_rel', sa.String(length=512), nullable=False),
            sa.Column('file_hash', sa.String(length=32), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint('spatial_position >= 1 AND spatial_position <= 9', name='ck_encounter_set_image_position_range'),
            sa.ForeignKeyConstraint(['patient_encounter_id'], ['patient_encounters.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('patient_encounter_id', 'spatial_position', name='uq_encounter_set_image_position')
        )
        op.create_index(op.f('ix_encounter_set_images_file_hash'), 'encounter_set_images', ['file_hash'], unique=False)
        op.create_index(op.f('ix_encounter_set_images_patient_encounter_id'), 'encounter_set_images', ['patient_encounter_id'], unique=False)
        op.create_index(op.f('ix_encounter_set_images_uuid'), 'encounter_set_images', ['uuid'], unique=True)

    # 2. Update diseases table
    columns_diseases = [c['name'] for c in inspector.get_columns('diseases')]
    if 'grading_scope' not in columns_diseases:
        op.add_column('diseases', sa.Column('grading_scope', sa.String(length=20), server_default='image', nullable=False))

    # 3. Update patient_encounters table
    columns_pe = [c['name'] for c in inspector.get_columns('patient_encounters')]
    if 'is_set_based' not in columns_pe:
        op.add_column('patient_encounters', sa.Column('is_set_based', sa.Boolean(), server_default='false', nullable=False))
    
    # Make zip_file_id nullable
    op.alter_column('patient_encounters', 'zip_file_id',
               existing_type=sa.INTEGER(),
               nullable=True)

    # 4. Update grading_tasks table
    columns_gt = [c['name'] for c in inspector.get_columns('grading_tasks')]
    if 'patient_encounter_id' not in columns_gt:
        op.add_column('grading_tasks', sa.Column('patient_encounter_id', sa.Integer(), nullable=True))
        op.create_index(op.f('ix_grading_tasks_patient_encounter_id'), 'grading_tasks', ['patient_encounter_id'], unique=False)
        op.create_unique_constraint('uq_task_patient_encounter_disease', 'grading_tasks', ['patient_encounter_id', 'disease_id'])
        op.create_foreign_key('fk_grading_tasks_patient_encounter', 'grading_tasks', 'patient_encounters', ['patient_encounter_id'], ['id'], ondelete='CASCADE')

    # 5. Fix type mismatch in s3_configs (if needed)
    columns_s3 = [c for c in inspector.get_columns('s3_configs') if c['name'] == 'rotation_time']
    if columns_s3 and not isinstance(columns_s3[0]['type'], sa.String):
        op.alter_column('s3_configs', 'rotation_time',
               existing_type=postgresql.TIME(),
               type_=sa.String(length=8),
               existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # 4. Update grading_tasks table
    tables = inspector.get_table_names()
    if 'grading_tasks' in tables:
        columns_gt = [c['name'] for c in inspector.get_columns('grading_tasks')]
        if 'patient_encounter_id' in columns_gt:
            op.drop_constraint('fk_grading_tasks_patient_encounter', 'grading_tasks', type_='foreignkey')
            op.drop_constraint('uq_task_patient_encounter_disease', 'grading_tasks', type_='unique')
            op.drop_index(op.f('ix_grading_tasks_patient_encounter_id'), table_name='grading_tasks')
            op.drop_column('grading_tasks', 'patient_encounter_id')
    
    # 3. Update patient_encounters table
    if 'patient_encounters' in tables:
        columns_pe = [c['name'] for c in inspector.get_columns('patient_encounters')]
        op.alter_column('patient_encounters', 'zip_file_id',
                   existing_type=sa.INTEGER(),
                   nullable=False)
        if 'is_set_based' in columns_pe:
            op.drop_column('patient_encounters', 'is_set_based')
    
    # 2. Update diseases table
    if 'diseases' in tables:
        columns_diseases = [c['name'] for c in inspector.get_columns('diseases')]
        if 'grading_scope' in columns_diseases:
            op.drop_column('diseases', 'grading_scope')
    
    # 1. Create encounter_set_images table
    if 'encounter_set_images' in tables:
        op.drop_index(op.f('ix_encounter_set_images_uuid'), table_name='encounter_set_images')
        op.drop_index(op.f('ix_encounter_set_images_patient_encounter_id'), table_name='encounter_set_images')
        op.drop_index(op.f('ix_encounter_set_images_file_hash'), table_name='encounter_set_images')
        op.drop_table('encounter_set_images')
