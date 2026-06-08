"""Add image scheme auto-create policy for EncounterSet packages.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b9
Create Date: 2026-06-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "upload_profile_est_package_image_schemes"
COLUMN_NAME = "auto_create_policy"
CHECK_NAME = "ck_up_est_pkg_image_auto_create_policy"
CHECK_SQL = "auto_create_policy IN ('never','always','remidio_dr_report_present','remidio_glaucoma_report_present')"


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
            sa.Column(COLUMN_NAME, sa.String(length=64), nullable=False, server_default="always"),
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
