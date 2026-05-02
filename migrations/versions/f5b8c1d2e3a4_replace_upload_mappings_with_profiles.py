"""replace upload mappings with upload profiles

Revision ID: f5b8c1d2e3a4
Revises: f4a9c2d1e8b6
Create Date: 2026-05-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f5b8c1d2e3a4"
down_revision: Union[str, Sequence[str], None] = "f4a9c2d1e8b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPLOAD_KIND_CHECK = "upload_kind IN ('direct_image','pregraded','remidio','encounter_set')"


def _tables(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _has_index(conn, table_name: str, index_name: str) -> bool:
    return op.get_context().dialect.has_index(conn, table_name, index_name)


def _create_index(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if table_name in _tables(conn) and not _has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_legacy_upload_mapping_tables(conn) -> None:
    for table_name in ("upload_mapping_areas", "upload_mapping_cameras", "upload_mappings"):
        if table_name in _tables(conn):
            op.drop_table(table_name)


def upgrade() -> None:
    conn = op.get_bind()

    if "upload_profiles" not in _tables(conn):
        op.create_table(
            "upload_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("allow_mydriatic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_non_mydriatic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("default_is_mydriatic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="CASCADE", name="fk_upload_profiles_lab_unit_id_lab_units"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_upload_profiles_project_id_projects"),
            sa.UniqueConstraint("lab_unit_id", "project_id", "name", name="uq_upload_profile_lab_project_name"),
            sa.CheckConstraint("(allow_mydriatic = true) OR (allow_non_mydriatic = true)", name="ck_upload_profile_allows_any_mydriatic_state"),
            sa.CheckConstraint("(default_is_mydriatic = false) OR (allow_mydriatic = true)", name="ck_upload_profile_default_mydriatic_allowed"),
            sa.CheckConstraint("(default_is_mydriatic = true) OR (allow_non_mydriatic = true)", name="ck_upload_profile_default_nonmydriatic_allowed"),
        )
    _create_index(conn, "ix_upload_profiles_lab_unit_id", "upload_profiles", ["lab_unit_id"])
    _create_index(conn, "ix_upload_profiles_project_id", "upload_profiles", ["project_id"])
    _create_index(conn, "ix_upload_profiles_active", "upload_profiles", ["active"])
    _create_index(conn, "ix_upload_profiles_lab_project_active", "upload_profiles", ["lab_unit_id", "project_id", "active"])

    _create_child_tables(conn)
    _add_profile_columns(conn)
    _drop_legacy_upload_mapping_tables(conn)


def _create_child_tables(conn) -> None:
    if "upload_profile_assignments" not in _tables(conn):
        op.create_table(
            "upload_profile_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], ondelete="CASCADE", name="fk_upload_profile_assignments_profile"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_upload_profile_assignments_user"),
            sa.UniqueConstraint("upload_profile_id", "user_id", name="uq_upload_profile_assignment_user"),
        )
    _create_index(conn, "ix_upload_profile_assignments_upload_profile_id", "upload_profile_assignments", ["upload_profile_id"])
    _create_index(conn, "ix_upload_profile_assignments_user_id", "upload_profile_assignments", ["user_id"])
    _create_index(conn, "ix_upload_profile_assignments_active", "upload_profile_assignments", ["active"])
    _create_index(conn, "ix_upload_profile_assignments_user_active", "upload_profile_assignments", ["user_id", "active"])

    for table_name, target_table, target_column, unique_name in (
        ("upload_profile_diseases", "diseases", "disease_id", "uq_upload_profile_disease"),
        ("upload_profile_cameras", "cameras", "camera_id", "uq_upload_profile_camera"),
        ("upload_profile_areas", "areas", "area_id", "uq_upload_profile_area"),
    ):
        if table_name not in _tables(conn):
            op.create_table(
                table_name,
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column("upload_profile_id", sa.Integer(), nullable=False),
                sa.Column(target_column, sa.Integer(), nullable=False),
                *( [sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false"))] if table_name == "upload_profile_diseases" else [] ),
                sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], ondelete="CASCADE", name=f"fk_{table_name}_profile"),
                sa.ForeignKeyConstraint([target_column], [f"{target_table}.id"], ondelete="CASCADE", name=f"fk_{table_name}_{target_column}"),
                sa.UniqueConstraint("upload_profile_id", target_column, name=unique_name),
            )
        _create_index(conn, f"ix_{table_name}_upload_profile_id", table_name, ["upload_profile_id"])
        _create_index(conn, f"ix_{table_name}_{target_column}", table_name, [target_column])
    _create_index(conn, "ix_upload_profile_diseases_profile_default", "upload_profile_diseases", ["upload_profile_id", "is_default"])

    if "upload_profile_kinds" not in _tables(conn):
        op.create_table(
            "upload_profile_kinds",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], ondelete="CASCADE", name="fk_upload_profile_kinds_profile"),
            sa.UniqueConstraint("upload_profile_id", "upload_kind", name="uq_upload_profile_kind"),
            sa.CheckConstraint(UPLOAD_KIND_CHECK, name="ck_upload_profile_kind_valid"),
        )
    _create_index(conn, "ix_upload_profile_kinds_upload_profile_id", "upload_profile_kinds", ["upload_profile_id"])
    _create_index(conn, "ix_upload_profile_kinds_upload_kind", "upload_profile_kinds", ["upload_kind"])

    if "upload_profile_ai_workflows" not in _tables(conn):
        op.create_table(
            "upload_profile_ai_workflows",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("ai_model_id", sa.Integer(), nullable=False),
            sa.Column("upload_kind", sa.String(length=32), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], ondelete="CASCADE", name="fk_upload_profile_ai_workflows_profile"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="CASCADE", name="fk_upload_profile_ai_workflows_disease"),
            sa.ForeignKeyConstraint(["ai_model_id"], ["ai_models.id"], ondelete="CASCADE", name="fk_upload_profile_ai_workflows_ai_model"),
            sa.UniqueConstraint("upload_profile_id", "disease_id", "ai_model_id", "upload_kind", name="uq_upload_profile_ai_workflow"),
            sa.CheckConstraint(UPLOAD_KIND_CHECK, name="ck_upload_profile_ai_workflow_kind_valid"),
        )
    for column_name in ("upload_profile_id", "disease_id", "ai_model_id", "upload_kind", "active"):
        _create_index(conn, f"ix_upload_profile_ai_workflows_{column_name}", "upload_profile_ai_workflows", [column_name])

    if "patient_encounter_target_diseases" not in _tables(conn):
        op.create_table(
            "patient_encounter_target_diseases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["patient_encounter_id"], ["patient_encounters.id"], ondelete="CASCADE", name="fk_patient_encounter_target_diseases_encounter"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="CASCADE", name="fk_patient_encounter_target_diseases_disease"),
            sa.UniqueConstraint("patient_encounter_id", "disease_id", name="uq_patient_encounter_target_disease"),
        )
    _create_index(conn, "ix_patient_encounter_target_diseases_patient_encounter_id", "patient_encounter_target_diseases", ["patient_encounter_id"])
    _create_index(conn, "ix_patient_encounter_target_diseases_disease_id", "patient_encounter_target_diseases", ["disease_id"])
    _create_index(conn, "ix_patient_encounter_target_disease_default", "patient_encounter_target_diseases", ["patient_encounter_id", "is_default"])


def _add_profile_columns(conn) -> None:
    if "patient_encounters" in _tables(conn) and "upload_profile_id" not in _columns(conn, "patient_encounters"):
        op.add_column("patient_encounters", sa.Column("upload_profile_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_patient_encounters_upload_profile_id_upload_profiles", "patient_encounters", "upload_profiles", ["upload_profile_id"], ["id"], ondelete="SET NULL")
    _create_index(conn, "ix_patient_encounters_upload_profile_id", "patient_encounters", ["upload_profile_id"])

    if "encounter_set_images" in _tables(conn):
        for column_name, ref_table in (("camera_id", "cameras"), ("area_id", "areas")):
            if column_name not in _columns(conn, "encounter_set_images"):
                op.add_column("encounter_set_images", sa.Column(column_name, sa.Integer(), nullable=True))
                op.create_foreign_key(f"fk_encounter_set_images_{column_name}_{ref_table}", "encounter_set_images", ref_table, [column_name], ["id"], ondelete="SET NULL")
            _create_index(conn, f"ix_encounter_set_images_{column_name}", "encounter_set_images", [column_name])
        if "is_mydriatic" not in _columns(conn, "encounter_set_images"):
            op.add_column("encounter_set_images", sa.Column("is_mydriatic", sa.Boolean(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if "encounter_set_images" in _tables(conn):
        for column_name in ("is_mydriatic", "area_id", "camera_id"):
            if column_name in _columns(conn, "encounter_set_images"):
                op.drop_column("encounter_set_images", column_name)
    if "patient_encounters" in _tables(conn) and "upload_profile_id" in _columns(conn, "patient_encounters"):
        op.drop_column("patient_encounters", "upload_profile_id")
    for table_name in (
        "patient_encounter_target_diseases",
        "upload_profile_ai_workflows",
        "upload_profile_kinds",
        "upload_profile_areas",
        "upload_profile_cameras",
        "upload_profile_diseases",
        "upload_profile_assignments",
        "upload_profiles",
    ):
        if table_name in _tables(conn):
            op.drop_table(table_name)
