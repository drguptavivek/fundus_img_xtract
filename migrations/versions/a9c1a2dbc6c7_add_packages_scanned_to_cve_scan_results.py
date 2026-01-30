"""add packages_scanned to CVE scan results

Revision ID: a9c1a2dbc6c7
Revises: cve_schedule_001
Create Date: 2026-01-30 04:29:21.210234

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9c1a2dbc6c7'
down_revision: Union[str, Sequence[str], None] = 'cve_schedule_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add packages scanned tracking to CVE scan results."""
    # Check if columns exist before adding (idempotent)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('cve_scan_results')]

    # Add packages_scanned_count with default for existing rows
    if 'packages_scanned_count' not in columns:
        op.add_column(
            'cve_scan_results',
            sa.Column('packages_scanned_count', sa.Integer(), server_default='0', nullable=False)
        )

    if 'packages_scanned_json' not in columns:
        op.add_column(
            'cve_scan_results',
            sa.Column('packages_scanned_json', sa.Text(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema - remove packages scanned tracking."""
    op.drop_column('cve_scan_results', 'packages_scanned_json')
    op.drop_column('cve_scan_results', 'packages_scanned_count')
