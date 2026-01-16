"""add dataset share and export tracking

Revision ID: c2d8f0a5b9d1
Revises: 45cf0f839a1c
Create Date: 2026-01-16 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d8f0a5b9d1"
down_revision: Union[str, Sequence[str], None] = "45cf0f839a1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    def _create_table(table_name: str, *args: object, **kwargs: object) -> None:
        if table_name in existing_tables:
            return
        op.create_table(table_name, *args, **kwargs)
        existing_tables.add(table_name)

    def _create_index(index_name: str, table_name: str, columns: list[str], **kwargs: object) -> None:
        if table_name not in existing_tables:
            return
        if op.get_context().dialect.has_index(conn, table_name, index_name):
            return
        op.create_index(index_name, table_name, columns, **kwargs)

    _create_table(
        "dataset_exports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_id"], ["curated_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_dataset_exports_job_id"),
    )
    _create_index(op.f("ix_dataset_exports_dataset_id"), "dataset_exports", ["dataset_id"], unique=False)
    _create_index(op.f("ix_dataset_exports_job_id"), "dataset_exports", ["job_id"], unique=True)
    _create_index(
        op.f("ix_dataset_exports_created_by_user_id"),
        "dataset_exports",
        ["created_by_user_id"],
        unique=False,
    )

    _create_table(
        "dataset_shares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("otp_hash", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("created_for", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["curated_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_dataset_shares_token_hash"),
    )
    _create_index(op.f("ix_dataset_shares_dataset_id"), "dataset_shares", ["dataset_id"], unique=False)
    _create_index(op.f("ix_dataset_shares_expires_at"), "dataset_shares", ["expires_at"], unique=False)
    _create_index(op.f("ix_dataset_shares_token_hash"), "dataset_shares", ["token_hash"], unique=True)
    _create_index(
        "ix_dataset_shares_dataset_active",
        "dataset_shares",
        ["dataset_id", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_dataset_shares_dataset_active", table_name="dataset_shares")
    op.drop_index(op.f("ix_dataset_shares_token_hash"), table_name="dataset_shares")
    op.drop_index(op.f("ix_dataset_shares_expires_at"), table_name="dataset_shares")
    op.drop_index(op.f("ix_dataset_shares_dataset_id"), table_name="dataset_shares")
    op.drop_table("dataset_shares")

    op.drop_index(op.f("ix_dataset_exports_created_by_user_id"), table_name="dataset_exports")
    op.drop_index(op.f("ix_dataset_exports_job_id"), table_name="dataset_exports")
    op.drop_index(op.f("ix_dataset_exports_dataset_id"), table_name="dataset_exports")
    op.drop_table("dataset_exports")
