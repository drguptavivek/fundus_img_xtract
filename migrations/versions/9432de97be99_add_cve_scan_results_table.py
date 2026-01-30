"""Add CVE scan results table

Revision ID: 9432de97be99
Revises: c7f4a8e3d1b2
Create Date: 2026-01-30 03:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9432de97be99'
down_revision = 'c7f4a8e3d1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create cve_scan_results table
    op.create_table(
        'cve_scan_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scan_type', sa.String(length=20), nullable=False, server_default='scheduled'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='completed'),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('critical_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('high_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('medium_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('low_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('vulnerabilities_json', sa.Text(), nullable=True),
        sa.Column('raw_output', sa.Text(), nullable=True),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('triggered_by_user_id', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['triggered_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_cve_scan_results_scanned_at', 'cve_scan_results', ['scanned_at'])
    op.create_index('ix_cve_scan_results_scan_type', 'cve_scan_results', ['scan_type'])
    op.create_index('ix_cve_scan_results_triggered_by_user_id', 'cve_scan_results', ['triggered_by_user_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_cve_scan_results_triggered_by_user_id', table_name='cve_scan_results')
    op.drop_index('ix_cve_scan_results_scan_type', table_name='cve_scan_results')
    op.drop_index('ix_cve_scan_results_scanned_at', table_name='cve_scan_results')

    # Drop table
    op.drop_table('cve_scan_results')
