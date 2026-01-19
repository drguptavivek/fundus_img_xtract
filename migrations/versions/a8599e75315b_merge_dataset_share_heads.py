"""merge dataset share heads

Revision ID: a8599e75315b
Revises: 1c2f9a0c7f4e, 8f1b4d9c2e71
Create Date: 2026-01-19 04:58:03.020872

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'a8599e75315b'
down_revision: Union[str, Sequence[str], None] = ('1c2f9a0c7f4e', '8f1b4d9c2e71')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    return


def downgrade() -> None:
    """Downgrade schema."""
    return
