"""seed regrade adjudicator role

Revision ID: c33fff63a0b2
Revises: b38338abed50
Create Date: 2026-02-07 13:11:04.469790

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c33fff63a0b2'
down_revision: Union[str, Sequence[str], None] = 'b38338abed50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        INSERT INTO roles (name)
        SELECT 'regrade_adjudicator'
        WHERE NOT EXISTS (
            SELECT 1 FROM roles WHERE name = 'regrade_adjudicator'
        );
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM roles WHERE name = 'regrade_adjudicator';")
