"""Add IP address to flask_sessions table

Revision ID: add_ip_address_to_flask_sessions
Revises: 691d42ba3fff
Create Date: 2025-11-09 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_ip_address_to_flask_sessions'
down_revision: Union[str, Sequence[str], None] = ('691d42ba3fff',)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add IP address column to flask_sessions table
    op.add_column('flask_sessions', sa.Column('ip_address', sa.String(length=45), nullable=True))

    # Create index for IP address for better performance
    op.create_index('ix_flask_sessions_ip_address', 'flask_sessions', ['ip_address'])


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the index first
    op.drop_index('ix_flask_sessions_ip_address', table_name='flask_sessions')

    # Remove the IP address column
    op.drop_column('flask_sessions', 'ip_address')