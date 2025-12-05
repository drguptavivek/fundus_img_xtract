"""add discrepancy and data exporter roles

Revision ID: 2c1a22fc75ac
Revises: 0d7513b7ef14
Create Date: 2025-12-05 03:50:03.299554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c1a22fc75ac"
down_revision: Union[str, Sequence[str], None] = "0d7513b7ef14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add discrepancy/data exporter roles if missing."""
    bind = op.get_bind()
    for role in ("discrepancy_reviewer", "data_exporter"):
        bind.execute(
            sa.text(
                "INSERT INTO roles (name) "
                "SELECT :name WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = :name)"
            ),
            {"name": role},
        )


def downgrade() -> None:
    """Remove discrepancy/data exporter roles."""
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM roles WHERE name IN (:r1, :r2)"),
        {"r1": "discrepancy_reviewer", "r2": "data_exporter"},
    )
