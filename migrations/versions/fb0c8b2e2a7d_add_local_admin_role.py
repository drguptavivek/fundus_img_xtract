"""Add local_admin role scoped to assigned lab units.

Revision ID: fb0c8b2e2a7d
Revises: d7e3fb45da1d
Create Date: 2025-11-30 12:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fb0c8b2e2a7d"
down_revision: Union[str, None] = "d7e3fb45da1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert the local_admin role if it does not already exist."""
    conn = op.get_bind()
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
    )

    exists = conn.execute(
        sa.select(roles_table.c.id).where(roles_table.c.name == "local_admin")
    ).scalar_one_or_none()

    if exists is None:
        conn.execute(sa.insert(roles_table).values(name="local_admin"))


def downgrade() -> None:
    """Remove the local_admin role."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM roles WHERE name = 'local_admin'"))
