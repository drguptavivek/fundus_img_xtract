"""add dataset share recipient email

Revision ID: 8f1b4d9c2e71
Revises: 4f2a1e9d2d68
Create Date: 2026-01-16 15:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f1b4d9c2e71"
down_revision: Union[str, Sequence[str], None] = "4f2a1e9d2d68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "dataset_shares",
        sa.Column("recipient_email", sa.String(length=254), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("dataset_shares", "recipient_email")
