"""Add EncounterSet task sampling policy.

Revision ID: a1b2c3d4e5fb
Revises: a1b2c3d4e5fa
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5fb"
down_revision = "a1b2c3d4e5fa"
branch_labels = None
depends_on = None


TABLE_NAME = "upload_profile_est_package_image_schemes"
CONTROL_COLUMN = "negative_controls_per_positive"
CONTROL_CHECK = "ck_up_est_pkg_image_negative_controls_per_positive"
CONTROL_CHECK_SQL = "negative_controls_per_positive >= 0 AND negative_controls_per_positive <= 20"
POLICY_CHECK = "ck_up_est_pkg_image_auto_create_policy"
POLICY_CHECK_UPGRADE = (
    "auto_create_policy IN ('never','always','remidio_dr_report_present',"
    "'remidio_amd_report_present','remidio_glaucoma_report_present','positive_plus_negative_controls')"
)
POLICY_CHECK_DOWNGRADE = (
    "auto_create_policy IN ('never','always','remidio_dr_report_present',"
    "'remidio_amd_report_present','remidio_glaucoma_report_present')"
)


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


def _replace_check(conn, table_name: str, check_name: str, condition: str) -> None:
    if table_name not in _tables(conn):
        return
    if check_name in _checks(conn, table_name):
        op.drop_constraint(check_name, table_name, type_="check")
    op.create_check_constraint(check_name, table_name, condition)


def upgrade():
    conn = op.get_bind()
    if TABLE_NAME not in _tables(conn):
        return
    if CONTROL_COLUMN not in _columns(conn, TABLE_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(CONTROL_COLUMN, sa.Integer(), nullable=False, server_default="0"),
        )
    _replace_check(conn, TABLE_NAME, POLICY_CHECK, POLICY_CHECK_UPGRADE)
    if CONTROL_CHECK not in _checks(conn, TABLE_NAME):
        op.create_check_constraint(CONTROL_CHECK, TABLE_NAME, CONTROL_CHECK_SQL)


def downgrade():
    conn = op.get_bind()
    if TABLE_NAME not in _tables(conn):
        return
    if POLICY_CHECK in _checks(conn, TABLE_NAME):
        op.execute(
            f"UPDATE {TABLE_NAME} SET auto_create_policy = 'always' "
            "WHERE auto_create_policy = 'positive_plus_negative_controls'"
        )
    _replace_check(conn, TABLE_NAME, POLICY_CHECK, POLICY_CHECK_DOWNGRADE)
    if CONTROL_CHECK in _checks(conn, TABLE_NAME):
        op.drop_constraint(CONTROL_CHECK, TABLE_NAME, type_="check")
    if CONTROL_COLUMN in _columns(conn, TABLE_NAME):
        op.drop_column(TABLE_NAME, CONTROL_COLUMN)
