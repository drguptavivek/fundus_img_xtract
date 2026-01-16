"""add dataset share download count

Revision ID: b1a9c8c4a955
Revises: c2d8f0a5b9d1
Create Date: 2026-01-16 14:40:10.197009
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1a9c8c4a955"
down_revision: Union[str, Sequence[str], None] = "c2d8f0a5b9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {col["name"] for col in inspector.get_columns("dataset_shares")}
    if "download_count" not in columns:
        op.add_column(
            "dataset_shares",
            sa.Column("download_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("dataset_shares", "download_count")
