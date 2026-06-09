"""Add Remidio OCR linkage to grading schemes.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "diseases"
COLUMN_NAME = "remidio_ocr_linkage"
CHECK_NAME = "ck_disease_remidio_ocr_linkage"
CHECK_SQL = "remidio_ocr_linkage IN ('none', 'dr', 'glaucoma')"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def _checks(conn, table_name: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in sa.inspect(conn).get_check_constraints(table_name)
        if constraint.get("name")
    }


def upgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in _tables(conn):
        return
    if COLUMN_NAME not in _columns(conn, TABLE_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(COLUMN_NAME, sa.String(length=32), nullable=False, server_default="none"),
        )
    if CHECK_NAME not in _checks(conn, TABLE_NAME):
        op.create_check_constraint(CHECK_NAME, TABLE_NAME, CHECK_SQL)


def downgrade() -> None:
    conn = op.get_bind()
    if TABLE_NAME not in _tables(conn):
        return
    if CHECK_NAME in _checks(conn, TABLE_NAME):
        op.execute(f"ALTER TABLE {TABLE_NAME} DROP CONSTRAINT IF EXISTS {CHECK_NAME}")
    if COLUMN_NAME in _columns(conn, TABLE_NAME):
        op.drop_column(TABLE_NAME, COLUMN_NAME)
