"""Add password_salt field to email_settings table for per-record encryption salts

Revision ID: 2e82ab9a8980
Revises: 86eca6cd0465
Create Date: 2025-11-20 08:54:59.832538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e82ab9a8980'
down_revision: Union[str, Sequence[str], None] = '86eca6cd0465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add password_salt column to email_settings table
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {column["name"] for column in inspector.get_columns("email_settings")}

    if "password_salt" not in columns:
        op.add_column('email_settings', sa.Column('password_salt', sa.String(length=64), nullable=True))

    # Add index for faster lookups if needed
    if not op.get_context().dialect.has_index(conn, "email_settings", "idx_email_settings_password_salt"):
        op.create_index('idx_email_settings_password_salt', 'email_settings', ['password_salt'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove index
    op.drop_index('idx_email_settings_password_salt', table_name='email_settings')

    # Remove password_salt column
    op.drop_column('email_settings', 'password_salt')
