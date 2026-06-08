"""Add EncounterSet grading package configuration and runtime targets.

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a7
Create Date: 2026-06-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f6a7b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PACKAGE_APPLICABILITY_CHECK = (
    "applicability IN ('always','remidio_dr_report_present','remidio_glaucoma_report_present','manual_only','disabled')"
)
IMAGE_SCHEME_AUTO_CREATE_POLICY_CHECK = (
    "auto_create_policy IN ('never','always','remidio_dr_report_present','remidio_glaucoma_report_present')"
)


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def _constraints(conn, table_name: str) -> set[str]:
    inspector = sa.inspect(conn)
    names = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
    names.update(constraint["name"] for constraint in inspector.get_check_constraints(table_name))
    names.update(constraint["name"] for constraint in inspector.get_foreign_keys(table_name))
    return {name for name in names if name}


def _indexes(conn, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}


def _create_index(conn, name: str, table_name: str, columns: list[str]) -> None:
    if name not in _indexes(conn, table_name):
        op.create_index(name, table_name, columns)


def _create_fk(conn, name: str, table_name: str, columns: list[str], remote_table: str, remote_columns: list[str], *, ondelete: str | None = None) -> None:
    if name not in _constraints(conn, table_name):
        op.create_foreign_key(name, table_name, remote_table, columns, remote_columns, ondelete=ondelete)


def _create_unique(conn, name: str, table_name: str, columns: list[str]) -> None:
    if name not in _constraints(conn, table_name):
        op.create_unique_constraint(name, table_name, columns)


def _create_check(conn, name: str, table_name: str, condition: str) -> None:
    if name not in _constraints(conn, table_name):
        op.create_check_constraint(name, table_name, condition)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if name in _indexes(conn, table_name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    conn = op.get_bind()
    table_names = _tables(conn)

    if "upload_profile_est_grading_packages" not in table_names:
        op.create_table(
            "upload_profile_est_grading_packages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_profile_encounter_set_type_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("applicability", sa.String(length=64), nullable=False, server_default="always"),
            sa.Column("default_image_grading_scheme_id", sa.Integer(), nullable=True),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["upload_profile_encounter_set_type_id"], ["upload_profile_encounter_set_types.id"], ondelete="CASCADE", name="fk_up_est_grading_pkg_mapping"),
            sa.ForeignKeyConstraint(["default_image_grading_scheme_id"], ["diseases.id"], ondelete="RESTRICT", name="fk_up_est_grading_pkg_default_image_scheme"),
            sa.UniqueConstraint("upload_profile_encounter_set_type_id", "code", name="uq_up_est_grading_package_code"),
            sa.CheckConstraint(PACKAGE_APPLICABILITY_CHECK, name="ck_up_est_grading_package_applicability"),
        )
    _create_index(conn, "ix_up_est_grading_package_mapping_active", "upload_profile_est_grading_packages", ["upload_profile_encounter_set_type_id", "active"])
    _create_index(conn, "ix_up_est_gp_mapping_id", "upload_profile_est_grading_packages", ["upload_profile_encounter_set_type_id"])
    _create_index(conn, "ix_up_est_gp_default_image_id", "upload_profile_est_grading_packages", ["default_image_grading_scheme_id"])

    if "upload_profile_est_package_image_schemes" not in table_names:
        op.create_table(
            "upload_profile_est_package_image_schemes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("package_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("auto_create_policy", sa.String(length=64), nullable=False, server_default="always"),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["package_id"], ["upload_profile_est_grading_packages.id"], ondelete="CASCADE", name="fk_up_est_pkg_image_package"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT", name="fk_up_est_pkg_image_disease"),
            sa.UniqueConstraint("package_id", "disease_id", name="uq_up_est_pkg_image_scheme"),
            sa.CheckConstraint(IMAGE_SCHEME_AUTO_CREATE_POLICY_CHECK, name="ck_up_est_pkg_image_auto_create_policy"),
        )
    elif "auto_create_policy" not in _columns(conn, "upload_profile_est_package_image_schemes"):
        op.add_column(
            "upload_profile_est_package_image_schemes",
            sa.Column("auto_create_policy", sa.String(length=64), nullable=False, server_default="always"),
        )
    _create_check(
        conn,
        "ck_up_est_pkg_image_auto_create_policy",
        "upload_profile_est_package_image_schemes",
        IMAGE_SCHEME_AUTO_CREATE_POLICY_CHECK,
    )
    _create_index(conn, "ix_up_est_pkg_image_scheme_package_active", "upload_profile_est_package_image_schemes", ["package_id", "active"])
    _create_index(conn, "ix_up_est_pkg_img_package_id", "upload_profile_est_package_image_schemes", ["package_id"])
    _create_index(conn, "ix_up_est_pkg_img_disease_id", "upload_profile_est_package_image_schemes", ["disease_id"])

    if "upload_profile_est_package_encounter_schemes" not in table_names:
        op.create_table(
            "upload_profile_est_package_encounter_schemes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("package_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["package_id"], ["upload_profile_est_grading_packages.id"], ondelete="CASCADE", name="fk_up_est_pkg_encounter_package"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT", name="fk_up_est_pkg_encounter_disease"),
            sa.UniqueConstraint("package_id", "disease_id", name="uq_up_est_pkg_encounter_scheme"),
        )
    _create_index(conn, "ix_up_est_pkg_encounter_scheme_package_active", "upload_profile_est_package_encounter_schemes", ["package_id", "active"])
    _create_index(conn, "ix_up_est_pkg_enc_package_id", "upload_profile_est_package_encounter_schemes", ["package_id"])
    _create_index(conn, "ix_up_est_pkg_enc_disease_id", "upload_profile_est_package_encounter_schemes", ["disease_id"])

    if "encounter_set_grading_packages" not in table_names:
        op.create_table(
            "encounter_set_grading_packages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("uuid", sa.String(length=36), nullable=False),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("upload_profile_est_grading_package_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("applicability", sa.String(length=64), nullable=True),
            sa.Column("state", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.ForeignKeyConstraint(["patient_encounter_id"], ["patient_encounters.id"], ondelete="CASCADE", name="fk_esgp_patient_encounter"),
            sa.ForeignKeyConstraint(["upload_profile_est_grading_package_id"], ["upload_profile_est_grading_packages.id"], ondelete="SET NULL", name="fk_esgp_config_package"),
            sa.UniqueConstraint("uuid", name="uq_encounter_set_grading_packages_uuid"),
            sa.UniqueConstraint("patient_encounter_id", "code", name="uq_encounter_set_grading_package_code"),
            sa.CheckConstraint("state IN ('pending','resident_done','resident2_done','arbitration','final')", name="ck_encounter_set_grading_package_state"),
        )
    _create_index(conn, "ix_encounter_set_grading_packages_uuid", "encounter_set_grading_packages", ["uuid"])
    _create_index(conn, "ix_encounter_set_grading_packages_patient_encounter_id", "encounter_set_grading_packages", ["patient_encounter_id"])
    _create_index(conn, "ix_esgp_config_package_id", "encounter_set_grading_packages", ["upload_profile_est_grading_package_id"])
    _create_index(conn, "ix_encounter_set_grading_packages_state", "encounter_set_grading_packages", ["state"])
    _create_index(conn, "ix_esgp_encounter_state", "encounter_set_grading_packages", ["patient_encounter_id", "state"])

    grading_columns = _columns(conn, "grading_tasks")
    if "encounter_set_image_id" not in grading_columns:
        op.add_column("grading_tasks", sa.Column("encounter_set_image_id", sa.Integer(), nullable=True))
    if "encounter_set_package_id" not in grading_columns:
        op.add_column("grading_tasks", sa.Column("encounter_set_package_id", sa.Integer(), nullable=True))
    if "grading_target_level" not in grading_columns:
        op.add_column("grading_tasks", sa.Column("grading_target_level", sa.String(length=24), nullable=True))
    if "task_source" not in grading_columns:
        op.add_column("grading_tasks", sa.Column("task_source", sa.String(length=64), nullable=True))

    _create_fk(conn, "fk_grading_tasks_encounter_set_image", "grading_tasks", ["encounter_set_image_id"], "encounter_set_images", ["id"], ondelete="CASCADE")
    _create_fk(conn, "fk_grading_tasks_encounter_set_package", "grading_tasks", ["encounter_set_package_id"], "encounter_set_grading_packages", ["id"], ondelete="CASCADE")
    _create_index(conn, "ix_grading_tasks_encounter_set_image_id", "grading_tasks", ["encounter_set_image_id"])
    _create_index(conn, "ix_grading_tasks_encounter_set_package_id", "grading_tasks", ["encounter_set_package_id"])
    _create_index(conn, "ix_grading_tasks_grading_target_level", "grading_tasks", ["grading_target_level"])
    _create_index(conn, "ix_grading_tasks_task_source", "grading_tasks", ["task_source"])
    _create_unique(conn, "uq_task_encounter_set_image_disease", "grading_tasks", ["encounter_set_image_id", "disease_id"])
    _create_unique(conn, "uq_task_encounter_set_package_target", "grading_tasks", ["encounter_set_package_id", "patient_encounter_id", "encounter_set_image_id", "disease_id", "grading_target_level"])

    for name in (
        "ck_grading_task_source_polymorphic",
        "ck_grading_task_one_image_ref",
        "ck_grading_task_either_encounter_or_direct",
    ):
        op.execute(f"ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS {name}")
    op.create_check_constraint(
        "ck_grading_task_source_polymorphic",
        "grading_tasks",
        "(encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NULL AND encounter_set_image_id IS NULL) OR "
        "(encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL AND patient_encounter_id IS NULL AND encounter_set_image_id IS NULL) OR "
        "(encounter_file_id IS NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NOT NULL AND encounter_set_image_id IS NULL) OR "
        "(encounter_file_id IS NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NULL AND encounter_set_image_id IS NOT NULL)",
    )
    _create_check(conn, "ck_task_grading_target_level_valid", "grading_tasks", "grading_target_level IS NULL OR grading_target_level IN ('image','encounter')")


def downgrade() -> None:
    conn = op.get_bind()
    if "grading_tasks" in _tables(conn):
        op.execute("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS ck_task_grading_target_level_valid")
        op.execute("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS ck_grading_task_source_polymorphic")
        op.execute("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS uq_task_encounter_set_package_target")
        op.execute("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS uq_task_encounter_set_image_disease")
        op.execute("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS fk_grading_tasks_encounter_set_package")
        op.execute("ALTER TABLE grading_tasks DROP CONSTRAINT IF EXISTS fk_grading_tasks_encounter_set_image")
        for index_name in (
            "ix_grading_tasks_task_source",
            "ix_grading_tasks_grading_target_level",
            "ix_grading_tasks_encounter_set_package_id",
            "ix_grading_tasks_encounter_set_image_id",
        ):
            _drop_index_if_exists(conn, index_name, "grading_tasks")
        columns = _columns(conn, "grading_tasks")
        for column_name in ("task_source", "grading_target_level", "encounter_set_package_id", "encounter_set_image_id"):
            if column_name in columns:
                op.drop_column("grading_tasks", column_name)
        op.create_check_constraint(
            "ck_grading_task_source_polymorphic",
            "grading_tasks",
            "(encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL AND patient_encounter_id IS NULL) OR "
            "(encounter_file_id IS NULL AND direct_image_upload_id IS NULL AND patient_encounter_id IS NOT NULL)",
        )

        for table_name in (
        "encounter_set_grading_packages",
        "upload_profile_est_package_encounter_schemes",
        "upload_profile_est_package_image_schemes",
        "upload_profile_est_grading_packages",
    ):
            if table_name in _tables(conn):
                op.drop_table(table_name)
