"""Merge heads for encounter set workflow

Revision ID: 7f5183911935
Revises: 7e2a1b3c4d5e, package_update_scanner_002
Create Date: 2026-01-31 02:20:27.765649

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f5183911935'
down_revision: Union[str, Sequence[str], None] = ('7e2a1b3c4d5e', 'package_update_scanner_002')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
