"""add sctid to upload metadata fields

Revision ID: b6e4f2a1c9d8
Revises: a4b2c8d9e1f3
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "b6e4f2a1c9d8"
down_revision: Union[str, Sequence[str], None] = "a4b2c8d9e1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str]) -> None:
    if table_name in _table_names(conn) and not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    conn = op.get_bind()
    if "upload_metadata_field_definitions" not in _table_names(conn):
        return
    if "sctid" not in _column_names(conn, "upload_metadata_field_definitions"):
        op.add_column("upload_metadata_field_definitions", sa.Column("sctid", sa.String(length=32), nullable=True))
    _create_index_if_missing(conn, "ix_upload_metadata_field_definitions_sctid", "upload_metadata_field_definitions", ["sctid"])


def downgrade() -> None:
    conn = op.get_bind()
    if "upload_metadata_field_definitions" not in _table_names(conn):
        return
    _drop_index_if_exists(conn, "ix_upload_metadata_field_definitions_sctid", "upload_metadata_field_definitions")
    if "sctid" in _column_names(conn, "upload_metadata_field_definitions"):
        op.drop_column("upload_metadata_field_definitions", "sctid")
