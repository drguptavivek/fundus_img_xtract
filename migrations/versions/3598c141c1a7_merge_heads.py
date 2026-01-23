"""merge heads

Revision ID: 3598c141c1a7
Revises: b1e7f36c2a4d, f2f1b7c68d2a
Create Date: 2026-01-23 11:40:54.528760

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3598c141c1a7'
down_revision: Union[str, Sequence[str], None] = ('b1e7f36c2a4d', 'f2f1b7c68d2a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
