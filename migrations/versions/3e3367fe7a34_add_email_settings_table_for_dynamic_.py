"""Add email_settings table for dynamic email configuration

Revision ID: 3e3367fe7a34
Revises: 819e7a97ca1f
Create Date: 2025-11-20 07:28:44.541770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e3367fe7a34'
down_revision: Union[str, Sequence[str], None] = '819e7a97ca1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create email_settings table
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

    _create_table('email_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('smtp_server', sa.String(length=255), nullable=False, server_default='localhost'),
        sa.Column('smtp_port', sa.Integer(), nullable=False, server_default='587'),
        sa.Column('smtp_username', sa.String(length=255), nullable=False),
        sa.Column('smtp_password', sa.String(length=255), nullable=False),
        sa.Column('from_email', sa.String(length=254), nullable=False),
        sa.Column('use_tls', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('use_ssl', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('verify_certificates', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('debug_logging', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('connection_timeout', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(now() at time zone \'utc\')'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(now() at time zone \'utc\')'), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.CheckConstraint('connection_timeout > 0 AND connection_timeout <= 300', name='check_connection_timeout_range'),
        sa.CheckConstraint('not (use_tls and use_ssl)', name='check_mutually_exclusive_tls_ssl'),
        sa.CheckConstraint('smtp_port > 0 AND smtp_port <= 65535', name='check_smtp_port_range'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    _create_index('ix_email_settings_active', 'email_settings', ['is_active'], unique=False)
    _create_index('ix_email_settings_updated', 'email_settings', ['updated_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_email_settings_updated', table_name='email_settings')
    op.drop_index('ix_email_settings_active', table_name='email_settings')

    # Drop table
    op.drop_table('email_settings')
