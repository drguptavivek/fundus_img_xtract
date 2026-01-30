"""Create package_update_scans table

Revision ID: package_update_scanner_001
Revises: a9c1a2dbc6c7
Create Date: 2026-01-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'package_update_scanner_001'
down_revision: Union[str, Sequence[str], None] = 'a9c1a2dbc6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create package_update_scans table."""
    # Check if table exists before creating (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'package_update_scans' not in inspector.get_table_names():
        op.execute("""
            CREATE TABLE package_update_scans (
                id SERIAL PRIMARY KEY,
                scanned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                scan_type VARCHAR(20) DEFAULT 'scheduled' NOT NULL,
                status VARCHAR(20) DEFAULT 'completed' NOT NULL,
                packages_scanned_count INTEGER DEFAULT 0 NOT NULL,
                updates_available_count INTEGER DEFAULT 0 NOT NULL,
                packages_json TEXT,
                error_message VARCHAR(500),
                triggered_by_user_id INTEGER REFERENCES users(id),
                duration_seconds INTEGER
            );
        """)

        # Create indexes for common queries
        op.execute("""
            CREATE INDEX ix_package_update_scans_scanned_at ON package_update_scans(scanned_at);
        """)
        op.execute("""
            CREATE INDEX ix_package_update_scans_scan_type ON package_update_scans(scan_type);
        """)
        op.execute("""
            CREATE INDEX ix_package_update_scans_triggered_by_user_id ON package_update_scans(triggered_by_user_id);
        """)


def downgrade() -> None:
    """Downgrade schema - drop package_update_scans table."""
    op.execute("""DROP TABLE IF EXISTS package_update_scans;""")
