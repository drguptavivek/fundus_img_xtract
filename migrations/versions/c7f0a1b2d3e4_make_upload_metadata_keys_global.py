"""make upload metadata field keys globally unique

Revision ID: c7f0a1b2d3e4
Revises: b6e4f2a1c9d8
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "c7f0a1b2d3e4"
down_revision: Union[str, Sequence[str], None] = "b6e4f2a1c9d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "upload_metadata_field_definitions"
OLD_CONSTRAINT = "uq_upload_metadata_field_definitions_scope_key"
NEW_CONSTRAINT = "uq_upload_metadata_field_definitions_key"


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _constraint_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {constraint["name"] for constraint in inspect(conn).get_unique_constraints(table_name)}


def _drop_unique_if_exists(conn, constraint_name: str) -> None:
    if constraint_name in _constraint_names(conn, TABLE_NAME):
        op.drop_constraint(constraint_name, TABLE_NAME, type_="unique")


def _create_unique_if_missing(conn, constraint_name: str, columns: list[str]) -> None:
    if constraint_name not in _constraint_names(conn, TABLE_NAME):
        op.create_unique_constraint(constraint_name, TABLE_NAME, columns)


def upgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in _table_names(conn):
        return
    _drop_unique_if_exists(conn, OLD_CONSTRAINT)
    op.execute(
        f"""
        WITH ranked AS (
            SELECT id, key, row_number() OVER (PARTITION BY key ORDER BY id) AS row_num
            FROM {TABLE_NAME}
        )
        UPDATE {TABLE_NAME} AS target
        SET key = left(target.key, 82) || '__dup_' || target.id::text
        FROM ranked
        WHERE target.id = ranked.id
          AND ranked.row_num > 1
        """
    )
    _create_unique_if_missing(conn, NEW_CONSTRAINT, ["key"])


def downgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in _table_names(conn):
        return
    _drop_unique_if_exists(conn, NEW_CONSTRAINT)
    _create_unique_if_missing(conn, OLD_CONSTRAINT, ["scope", "key"])
