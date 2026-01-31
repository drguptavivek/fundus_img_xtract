"""Add uuid to PatientEncounters

Revision ID: fc94d51475fd
Revises: 45867a4765ec
Create Date: 2026-01-31 02:40:41.359265

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = 'fc94d51475fd'
down_revision: Union[str, Sequence[str], None] = '45867a4765ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with idempotency and data safety."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # 1. Add uuid column if it doesn't exist
    columns = [c['name'] for c in inspector.get_columns('patient_encounters')]
    if 'uuid' not in columns:
        op.add_column('patient_encounters', sa.Column('uuid', sa.String(length=36), nullable=True))
    
    # 2. Populate NULL uuids using PostgreSQL's gen_random_uuid() or similar if available, 
    # but for portability and simplicity since we might not have pgcrypto, we use a loop or a direct update.
    # We'll use a cross-platform safe way within the migration.
    op.execute("""
        UPDATE patient_encounters 
        SET uuid = md5(random()::text || clock_timestamp()::text)::uuid::text 
        WHERE uuid IS NULL
    """)

    # 3. Set NOT NULL and add index if not present
    op.alter_column('patient_encounters', 'uuid', nullable=False)
    
    indices = [i['name'] for i in inspector.get_indexes('patient_encounters')]
    if 'ix_patient_encounters_uuid' not in indices:
        op.create_index(op.f('ix_patient_encounters_uuid'), 'patient_encounters', ['uuid'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    
    if 'patient_encounters' in tables:
        indices = [i['name'] for i in inspector.get_indexes('patient_encounters')]
        if 'ix_patient_encounters_uuid' in indices:
            op.drop_index(op.f('ix_patient_encounters_uuid'), table_name='patient_encounters')
            
        columns = [c['name'] for c in inspector.get_columns('patient_encounters')]
        if 'uuid' in columns:
            op.drop_column('patient_encounters', 'uuid')