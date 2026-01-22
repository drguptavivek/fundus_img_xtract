"""add_pii_override_fields

Revision ID: 79cc3b6a36ee
Revises: 2b691dfc8c46
Create Date: 2026-01-22 05:07:23.678675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = '79cc3b6a36ee'
down_revision: Union[str, Sequence[str], None] = '2b691dfc8c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = {col['name'] for col in inspector.get_columns('image_pii_verifications')}

    if 'source' not in columns:
        op.add_column(
            'image_pii_verifications',
            sa.Column('source', sa.String(length=16), server_default='auto', nullable=False),
        )
    if 'detections_json' not in columns:
        op.add_column(
            'image_pii_verifications',
            sa.Column('detections_json', sa.Text(), nullable=True),
        )
    if 'roi_json' not in columns:
        op.add_column(
            'image_pii_verifications',
            sa.Column('roi_json', sa.Text(), nullable=True),
        )

    if not op.get_context().dialect.has_index(conn, 'image_pii_verifications', 'ix_image_pii_verifications_source'):
        op.create_index(
            'ix_image_pii_verifications_source',
            'image_pii_verifications',
            ['source'],
            unique=False,
        )

    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='image_pii_verifications' AND column_name='source'
            ) THEN
                ALTER TABLE image_pii_verifications
                ALTER COLUMN source DROP DEFAULT;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = {col['name'] for col in inspector.get_columns('image_pii_verifications')}

    if op.get_context().dialect.has_index(conn, 'image_pii_verifications', 'ix_image_pii_verifications_source'):
        op.drop_index('ix_image_pii_verifications_source', table_name='image_pii_verifications')

    if 'roi_json' in columns:
        op.drop_column('image_pii_verifications', 'roi_json')
    if 'detections_json' in columns:
        op.drop_column('image_pii_verifications', 'detections_json')
    if 'source' in columns:
        op.drop_column('image_pii_verifications', 'source')
