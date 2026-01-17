"""Add dataset share terms acceptance tracking.

Revision ID: 1c2f9a0c7f4e
Revises: fb0c8b2e2a7d
Create Date: 2026-01-17 06:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c2f9a0c7f4e"
down_revision: Union[str, None] = "fb0c8b2e2a7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add terms acceptance metadata for dataset shares."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("dataset_shares")}

    if "terms_accepted_at" not in columns:
        op.add_column(
            "dataset_shares",
            sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "terms_accepted_ip" not in columns:
        op.add_column(
            "dataset_shares",
            sa.Column("terms_accepted_ip", sa.String(length=45), nullable=True),
        )


def downgrade() -> None:
    """Remove terms acceptance metadata from dataset shares."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("dataset_shares")}

    if "terms_accepted_ip" in columns:
        op.drop_column("dataset_shares", "terms_accepted_ip")
    if "terms_accepted_at" in columns:
        op.drop_column("dataset_shares", "terms_accepted_at")
