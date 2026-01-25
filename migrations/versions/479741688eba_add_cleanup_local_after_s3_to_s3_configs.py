"""add cleanup_local_after_s3 to s3_configs

Revision ID: 479741688eba
Revises: e1561a8ecbe7
Create Date: 2026-01-25 17:03:47.760894

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '479741688eba'
down_revision: Union[str, Sequence[str], None] = 'e1561a8ecbe7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cleanup_local_after_s3 column to s3_configs table.

    If True, this option enables automatic deletion of local files
    after successful S3 upload confirmation, reducing storage overhead.
    """
    # Check if column exists before adding (idempotent)
    conn = op.get_bind()
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Get existing columns
    columns_result = conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 's3_configs'
    """))
    existing_columns = {row[0] for row in columns_result}

    if 'cleanup_local_after_s3' not in existing_columns:
        op.add_column(
            's3_configs',
            sa.Column('cleanup_local_after_s3', sa.Boolean(), server_default='false', nullable=False)
        )


def downgrade() -> None:
    """Remove cleanup_local_after_s3 column from s3_configs table."""
    op.drop_column('s3_configs', 'cleanup_local_after_s3')
