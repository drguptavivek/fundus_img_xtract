"""Merge heads for centering and seed branches

Revision ID: 4c2c6f6e3a1b
Revises: 7e6d9c9b4d6d, 691d42ba3fff
Create Date: 2026-02-21 00:15:00.000000
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "4c2c6f6e3a1b"
down_revision: Union[str, Sequence[str], None] = ("7e6d9c9b4d6d", "691d42ba3fff")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge heads; no-op schema change."""
    pass


def downgrade() -> None:
    """Allow rollback to either parent head."""
    pass
