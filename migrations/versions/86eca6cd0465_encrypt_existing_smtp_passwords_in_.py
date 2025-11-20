"""Encrypt existing SMTP passwords in database

Revision ID: 86eca6cd0465
Revises: 3e3367fe7a34
Create Date: 2025-11-20 08:18:56.945248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86eca6cd0465'
down_revision: Union[str, Sequence[str], None] = '3e3367fe7a34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
