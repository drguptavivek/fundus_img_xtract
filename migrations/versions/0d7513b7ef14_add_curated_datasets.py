"""add curated datasets

Revision ID: 0d7513b7ef14
Revises: 8c00a6c7a8b8
Create Date: 2025-12-04 07:44:19.661076
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0d7513b7ef14"
down_revision: Union[str, Sequence[str], None] = "8c00a6c7a8b8"
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
        "curated_datasets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False),
        sa.Column("disease_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(
        op.f("ix_curated_datasets_created_by_user_id"),
        "curated_datasets",
        ["created_by_user_id"],
        unique=False,
    )
    _create_index(
        op.f("ix_curated_datasets_disease_id"),
        "curated_datasets",
        ["disease_id"],
        unique=False,
    )
    _create_index(op.f("ix_curated_datasets_uuid"), "curated_datasets", ["uuid"], unique=True)

    _create_table(
        "curated_dataset_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("include_in_export", sa.Boolean(), nullable=False),
        sa.Column("selection_method", sa.String(length=16), nullable=False),
        sa.Column("selected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("selection_method IN ('auto','manual')", name="ck_curated_dataset_items_method"),
        sa.ForeignKeyConstraint(["dataset_id"], ["curated_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["grading_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "task_id", name="uq_curated_dataset_items_dataset_task"),
    )
    _create_index(
        op.f("ix_curated_dataset_items_dataset_id"),
        "curated_dataset_items",
        ["dataset_id"],
        unique=False,
    )
    _create_index(
        op.f("ix_curated_dataset_items_selected_by_user_id"),
        "curated_dataset_items",
        ["selected_by_user_id"],
        unique=False,
    )
    _create_index(
        op.f("ix_curated_dataset_items_task_id"),
        "curated_dataset_items",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_curated_dataset_items_task_id"), table_name="curated_dataset_items")
    op.drop_index(
        op.f("ix_curated_dataset_items_selected_by_user_id"),
        table_name="curated_dataset_items",
    )
    op.drop_index(op.f("ix_curated_dataset_items_dataset_id"), table_name="curated_dataset_items")
    op.drop_table("curated_dataset_items")
    op.drop_index(op.f("ix_curated_datasets_uuid"), table_name="curated_datasets")
    op.drop_index(op.f("ix_curated_datasets_disease_id"), table_name="curated_datasets")
    op.drop_index(op.f("ix_curated_datasets_created_by_user_id"), table_name="curated_datasets")
    op.drop_table("curated_datasets")
