"""add upload profile task prioritization config

Revision ID: b7c8d9e0f1a2
Revises: a6d9e8f7c5b4
Create Date: 2026-05-23 06:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a6d9e8f7c5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "upload_profiles"
COLUMN_NAME = "task_prioritization_json"


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in _table_names(conn):
        return
    if COLUMN_NAME not in _column_names(conn, TABLE_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in _table_names(conn):
        return
    if COLUMN_NAME in _column_names(conn, TABLE_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
