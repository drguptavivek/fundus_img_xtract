"""add mobile upload idempotency

Revision ID: c4d5e6f7a8b9
Revises: b8c3d7f1e2a4
Create Date: 2026-05-03 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b8c3d7f1e2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "idempotency_key" not in _columns(inspector, "jobs"):
        op.add_column("jobs", sa.Column("idempotency_key", sa.String(length=80), nullable=True))
    _create_index_if_missing(inspector, "jobs", "ix_jobs_idempotency_key", ["idempotency_key"])
    _create_partial_unique_index_if_missing(
        inspector,
        "jobs",
        "uq_jobs_uploader_idempotency_key",
        ["uploader_user_id", "idempotency_key"],
        "idempotency_key IS NOT NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _drop_index_if_exists(inspector, "jobs", "uq_jobs_uploader_idempotency_key")
    _drop_index_if_exists(inspector, "jobs", "ix_jobs_idempotency_key")
    if "idempotency_key" in _columns(inspector, "jobs"):
        op.drop_column("jobs", "idempotency_key")


def _columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    if index_name not in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.create_index(index_name, table_name, columns)


def _create_partial_unique_index_if_missing(
    inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
    where_clause: str,
) -> None:
    if index_name not in {index["name"] for index in inspector.get_indexes(table_name)}:
        quoted_columns = ", ".join(columns)
        op.execute(f"CREATE UNIQUE INDEX {index_name} ON {table_name} ({quoted_columns}) WHERE {where_clause}")


def _drop_index_if_exists(inspector, table_name: str, index_name: str) -> None:
    if index_name in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.drop_index(index_name, table_name=table_name)
