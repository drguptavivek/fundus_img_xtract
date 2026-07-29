"""Add AMD Remidio report task policy.

Revision ID: a1b2c3d4e5fa
Revises: a1b2c3d4e5f9
Create Date: 2026-07-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5fa"
down_revision = "a1b2c3d4e5f9"
branch_labels = None
depends_on = None


DISEASE_TABLE = "diseases"
DISEASE_CHECK_NAME = "ck_disease_remidio_ocr_linkage"
DISEASE_CHECK_UPGRADE = "remidio_ocr_linkage IN ('none', 'dr', 'amd', 'glaucoma')"
DISEASE_CHECK_DOWNGRADE = "remidio_ocr_linkage IN ('none', 'dr', 'glaucoma')"

PACKAGE_TABLE = "upload_profile_est_grading_packages"
PACKAGE_CHECK_NAME = "ck_up_est_grading_package_applicability"
PACKAGE_CHECK_UPGRADE = (
    "applicability IN ('always','remidio_dr_report_present','remidio_amd_report_present',"
    "'remidio_glaucoma_report_present','manual_only','disabled')"
)
PACKAGE_CHECK_DOWNGRADE = (
    "applicability IN ('always','remidio_dr_report_present','remidio_glaucoma_report_present','manual_only','disabled')"
)

IMAGE_SCHEME_TABLE = "upload_profile_est_package_image_schemes"
IMAGE_SCHEME_CHECK_NAME = "ck_up_est_pkg_image_auto_create_policy"
IMAGE_SCHEME_CHECK_UPGRADE = (
    "auto_create_policy IN ('never','always','remidio_dr_report_present',"
    "'remidio_amd_report_present','remidio_glaucoma_report_present')"
)
IMAGE_SCHEME_CHECK_DOWNGRADE = (
    "auto_create_policy IN ('never','always','remidio_dr_report_present','remidio_glaucoma_report_present')"
)


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _checks(conn, table_name: str) -> set[str]:
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
    _replace_check(conn, DISEASE_TABLE, DISEASE_CHECK_NAME, DISEASE_CHECK_UPGRADE)
    _replace_check(conn, PACKAGE_TABLE, PACKAGE_CHECK_NAME, PACKAGE_CHECK_UPGRADE)
    _replace_check(conn, IMAGE_SCHEME_TABLE, IMAGE_SCHEME_CHECK_NAME, IMAGE_SCHEME_CHECK_UPGRADE)


def downgrade():
    conn = op.get_bind()
    if IMAGE_SCHEME_TABLE in _tables(conn):
        op.execute(
            f"UPDATE {IMAGE_SCHEME_TABLE} SET auto_create_policy = 'always' "
            "WHERE auto_create_policy = 'remidio_amd_report_present'"
        )
    if PACKAGE_TABLE in _tables(conn):
        op.execute(
            f"UPDATE {PACKAGE_TABLE} SET applicability = 'always' "
            "WHERE applicability = 'remidio_amd_report_present'"
        )
    if DISEASE_TABLE in _tables(conn):
        op.execute(f"UPDATE {DISEASE_TABLE} SET remidio_ocr_linkage = 'none' WHERE remidio_ocr_linkage = 'amd'")

    _replace_check(conn, IMAGE_SCHEME_TABLE, IMAGE_SCHEME_CHECK_NAME, IMAGE_SCHEME_CHECK_DOWNGRADE)
    _replace_check(conn, PACKAGE_TABLE, PACKAGE_CHECK_NAME, PACKAGE_CHECK_DOWNGRADE)
    _replace_check(conn, DISEASE_TABLE, DISEASE_CHECK_NAME, DISEASE_CHECK_DOWNGRADE)
