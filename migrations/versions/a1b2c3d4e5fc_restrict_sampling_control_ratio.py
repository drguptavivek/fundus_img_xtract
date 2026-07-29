"""Restrict sampling control ratio.

Revision ID: a1b2c3d4e5fc
Revises: a1b2c3d4e5fb
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5fc"
down_revision = "a1b2c3d4e5fb"
branch_labels = None
depends_on = None


TABLE_NAME = "upload_profile_est_package_image_schemes"
CONTROL_CHECK = "ck_up_est_pkg_image_negative_controls_per_positive"
CONTROL_CHECK_UPGRADE = (
    "((auto_create_policy = 'positive_plus_negative_controls' "
    "AND negative_controls_per_positive >= 1 "
    "AND negative_controls_per_positive <= 10) "
    "OR (auto_create_policy <> 'positive_plus_negative_controls' "
    "AND negative_controls_per_positive >= 0 "
    "AND negative_controls_per_positive <= 10))"
)
CONTROL_CHECK_DOWNGRADE = "negative_controls_per_positive >= 0 AND negative_controls_per_positive <= 20"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def _checks(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {
        constraint["name"]
        for constraint in sa.inspect(conn).get_check_constraints(table_name)
        if constraint.get("name")
    }


def _replace_check(conn, check_name: str, condition: str) -> None:
    if TABLE_NAME not in _tables(conn):
        return
    if check_name in _checks(conn, TABLE_NAME):
        op.drop_constraint(check_name, TABLE_NAME, type_="check")
    op.create_check_constraint(check_name, TABLE_NAME, condition)


def upgrade():
    conn = op.get_bind()
    if TABLE_NAME not in _tables(conn):
        return
    columns = _columns(conn, TABLE_NAME)
    if "auto_create_policy" not in columns or "negative_controls_per_positive" not in columns:
        return

    op.execute(
        f"""
        UPDATE {TABLE_NAME}
        SET negative_controls_per_positive = 3
        WHERE auto_create_policy = 'positive_plus_negative_controls'
          AND negative_controls_per_positive < 1
        """
    )
    op.execute(
        f"""
        UPDATE {TABLE_NAME}
        SET negative_controls_per_positive = 10
        WHERE negative_controls_per_positive > 10
        """
    )
    _replace_check(conn, CONTROL_CHECK, CONTROL_CHECK_UPGRADE)


def downgrade():
    conn = op.get_bind()
    if TABLE_NAME not in _tables(conn):
        return
    _replace_check(conn, CONTROL_CHECK, CONTROL_CHECK_DOWNGRADE)
