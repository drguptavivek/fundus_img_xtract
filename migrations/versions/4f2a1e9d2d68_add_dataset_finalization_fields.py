"""add dataset finalization fields

Revision ID: 4f2a1e9d2d68
Revises: b1a9c8c4a955
Create Date: 2026-01-16 14:55:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f2a1e9d2d68"
down_revision: Union[str, Sequence[str], None] = "b1a9c8c4a955"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "curated_datasets",
        sa.Column("is_finalized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "curated_datasets",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "curated_datasets",
        sa.Column("finalized_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_curated_datasets_finalized_by_user_id"),
        "curated_datasets",
        ["finalized_by_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_curated_datasets_finalized_by_user_id_users"),
        "curated_datasets",
        "users",
        ["finalized_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_curated_datasets_finalized_by_user_id_users"), "curated_datasets", type_="foreignkey")
    op.drop_index(op.f("ix_curated_datasets_finalized_by_user_id"), table_name="curated_datasets")
    op.drop_column("curated_datasets", "finalized_by_user_id")
    op.drop_column("curated_datasets", "finalized_at")
    op.drop_column("curated_datasets", "is_finalized")
