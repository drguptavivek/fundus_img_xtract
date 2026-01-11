"""add_hospital_isolation_to_users

Revision ID: 413938207fa4
Revises: 2c1a22fc75ac
Create Date: 2026-01-11 05:56:32.733880

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '413938207fa4'
down_revision: Union[str, Sequence[str], None] = '2c1a22fc75ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
