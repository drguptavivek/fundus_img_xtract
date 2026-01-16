"""add_sensitive_operations_audit_table

Revision ID: 7399d7a901ce
Revises: 342cde5afd2c
Create Date: 2026-01-11 09:19:40.547770

Bead: 5N-1 (fundus_img_xtract-1yu)
Reference: docs/PII_Exposure_Control_Policy.md Section 6A.3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7399d7a901ce'
down_revision: Union[str, Sequence[str], None] = '342cde5afd2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sensitive_operations_audit table for tracking sensitive data operations."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    def _create_table(table_name: str, *args: object, **kwargs: object) -> None:
        if table_name in existing_tables:
            return
        op.create_table(table_name, *args, **kwargs)
        existing_tables.add(table_name)

    def _create_index(index_name: str, table_name: str, columns: list[str], **kwargs: object) -> None:
        if table_name not in existing_tables:
            return
        if op.get_context().dialect.has_index(conn, table_name, index_name):
            return
        op.create_index(index_name, table_name, columns, **kwargs)

    _create_table('sensitive_operations_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('operation_type', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_details', sa.Text(), nullable=True),
        sa.Column('result_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    _create_index(
        op.f('ix_sensitive_operations_audit_created_at'), 
        'sensitive_operations_audit', 
        ['created_at'], 
        unique=False
    )
    _create_index(
        op.f('ix_sensitive_operations_audit_operation_type'), 
        'sensitive_operations_audit', 
        ['operation_type'], 
        unique=False
    )
    _create_index(
        op.f('ix_sensitive_operations_audit_status'), 
        'sensitive_operations_audit', 
        ['status'], 
        unique=False
    )
    _create_index(
        op.f('ix_sensitive_operations_audit_user_id'), 
        'sensitive_operations_audit', 
        ['user_id'], 
        unique=False
    )


def downgrade() -> None:
    """Drop sensitive_operations_audit table."""
    op.drop_index(op.f('ix_sensitive_operations_audit_user_id'), table_name='sensitive_operations_audit')
    op.drop_index(op.f('ix_sensitive_operations_audit_status'), table_name='sensitive_operations_audit')
    op.drop_index(op.f('ix_sensitive_operations_audit_operation_type'), table_name='sensitive_operations_audit')
    op.drop_index(op.f('ix_sensitive_operations_audit_created_at'), table_name='sensitive_operations_audit')
    op.drop_table('sensitive_operations_audit')
