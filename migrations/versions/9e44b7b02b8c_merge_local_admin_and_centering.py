"""Merge local_admin role branch with centering/seed branch

Revision ID: 9e44b7b02b8c
Revises: 4c2c6f6e3a1b, fb0c8b2e2a7d
Create Date: 2026-02-21 00:25:00.000000
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "9e44b7b02b8c"
down_revision: Union[str, Sequence[str], None] = ("4c2c6f6e3a1b", "fb0c8b2e2a7d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge heads; no schema changes."""
    pass


def downgrade() -> None:
    """Allow rollback to either parent head."""
    pass
