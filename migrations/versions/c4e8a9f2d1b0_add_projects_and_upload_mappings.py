"""add projects and upload mappings

Revision ID: c4e8a9f2d1b0
Revises: b3d4e5f6a7b8
Create Date: 2026-04-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "c4e8a9f2d1b0"
down_revision: Union[str, Sequence[str], None] = "b3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _fk_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {fk["name"] for fk in inspect(conn).get_foreign_keys(table_name)}


def _constraint_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    inspector = inspect(conn)
    names = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
    names.update(constraint["name"] for constraint in inspector.get_check_constraints(table_name))
    return names


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _add_project_fk_column(conn, table_name: str, fk_name: str, index_name: str) -> None:
    columns = _column_names(conn, table_name)
    if "project_id" not in columns:
        op.add_column(table_name, sa.Column("project_id", sa.Integer(), nullable=True))
    if fk_name not in _fk_names(conn, table_name):
        op.create_foreign_key(fk_name, table_name, "projects", ["project_id"], ["id"])
    _create_index_if_missing(conn, index_name, table_name, ["project_id"])


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if "projects" not in tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("title", name="uq_projects_title"),
            sa.UniqueConstraint("code", name="uq_projects_code"),
        )
    _create_index_if_missing(conn, "ix_projects_active", "projects", ["active"])

    if "project_investigators" not in _table_names(conn):
        op.create_table(
            "project_investigators",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=64), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint(
                "role IN ('principal_investigator','co_investigator','coordinator')",
                name="ck_project_investigator_role",
            ),
            sa.UniqueConstraint("project_id", "user_id", "role", name="uq_project_investigator_role"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_investigators_project_id_projects", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_project_investigators_user_id_users", ondelete="CASCADE"),
        )
    _create_index_if_missing(conn, "ix_project_investigators_project_id", "project_investigators", ["project_id"])
    _create_index_if_missing(conn, "ix_project_investigators_user_id", "project_investigators", ["user_id"])
    _create_index_if_missing(conn, "ix_project_investigators_active", "project_investigators", ["active"])
    _create_index_if_missing(conn, "ix_project_investigators_project_active", "project_investigators", ["project_id", "active"])
    _create_index_if_missing(conn, "ix_project_investigators_user_active", "project_investigators", ["user_id", "active"])

    if "upload_mappings" not in _table_names(conn):
        op.create_table(
            "upload_mappings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("default_disease_id", sa.Integer(), nullable=True),
            sa.Column("allow_mydriatic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_non_mydriatic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("default_is_mydriatic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint(
                "(allow_mydriatic = true) OR (allow_non_mydriatic = true)",
                name="ck_upload_mapping_allows_any_mydriatic_state",
            ),
            sa.CheckConstraint(
                "(default_is_mydriatic = false) OR (allow_mydriatic = true)",
                name="ck_upload_mapping_default_mydriatic_allowed",
            ),
            sa.CheckConstraint(
                "(default_is_mydriatic = true) OR (allow_non_mydriatic = true)",
                name="ck_upload_mapping_default_nonmydriatic_allowed",
            ),
            sa.UniqueConstraint(
                "user_id",
                "lab_unit_id",
                "project_id",
                "disease_id",
                name="uq_upload_mapping_user_lab_project_disease",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_upload_mappings_user_id_users", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], name="fk_upload_mappings_lab_unit_id_lab_units", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_upload_mappings_project_id_projects", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], name="fk_upload_mappings_disease_id_diseases", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["default_disease_id"], ["diseases.id"], name="fk_upload_mappings_default_disease_id_diseases", ondelete="RESTRICT"),
        )
    for column_name in ("user_id", "lab_unit_id", "project_id", "disease_id", "default_disease_id", "active"):
        _create_index_if_missing(conn, f"ix_upload_mappings_{column_name}", "upload_mappings", [column_name])
    _create_index_if_missing(conn, "ix_upload_mappings_user_project_active", "upload_mappings", ["user_id", "project_id", "active"])
    _create_index_if_missing(conn, "ix_upload_mappings_lab_project_active", "upload_mappings", ["lab_unit_id", "project_id", "active"])

    if "upload_mapping_cameras" not in _table_names(conn):
        op.create_table(
            "upload_mapping_cameras",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_mapping_id", sa.Integer(), nullable=False),
            sa.Column("camera_id", sa.Integer(), nullable=False),
            sa.UniqueConstraint("upload_mapping_id", "camera_id", name="uq_upload_mapping_camera"),
            sa.ForeignKeyConstraint(["upload_mapping_id"], ["upload_mappings.id"], name="fk_upload_mapping_cameras_mapping_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_upload_mapping_cameras_camera_id_cameras", ondelete="CASCADE"),
        )
    _create_index_if_missing(conn, "ix_upload_mapping_cameras_upload_mapping_id", "upload_mapping_cameras", ["upload_mapping_id"])
    _create_index_if_missing(conn, "ix_upload_mapping_cameras_camera_id", "upload_mapping_cameras", ["camera_id"])

    if "upload_mapping_areas" not in _table_names(conn):
        op.create_table(
            "upload_mapping_areas",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_mapping_id", sa.Integer(), nullable=False),
            sa.Column("area_id", sa.Integer(), nullable=False),
            sa.UniqueConstraint("upload_mapping_id", "area_id", name="uq_upload_mapping_area"),
            sa.ForeignKeyConstraint(["upload_mapping_id"], ["upload_mappings.id"], name="fk_upload_mapping_areas_mapping_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["area_id"], ["areas.id"], name="fk_upload_mapping_areas_area_id_areas", ondelete="CASCADE"),
        )
    _create_index_if_missing(conn, "ix_upload_mapping_areas_upload_mapping_id", "upload_mapping_areas", ["upload_mapping_id"])
    _create_index_if_missing(conn, "ix_upload_mapping_areas_area_id", "upload_mapping_areas", ["area_id"])

    _add_project_fk_column(conn, "jobs", "fk_jobs_project_id_projects", "ix_jobs_project_id")
    _add_project_fk_column(conn, "direct_image_uploads", "fk_direct_image_uploads_project_id_projects", "ix_direct_image_uploads_project_id")
    _add_project_fk_column(conn, "patient_encounters", "fk_patient_encounters_project_id_projects", "ix_patient_encounters_project_id")
    _add_project_fk_column(conn, "encounter_files", "fk_encounter_files_project_id_projects", "ix_encounter_files_project_id")
    _add_project_fk_column(conn, "encounter_file_pdfs", "fk_encounter_file_pdfs_project_id_projects", "ix_encounter_file_pdfs_project_id")
    _add_project_fk_column(conn, "encounter_set_images", "fk_encounter_set_images_project_id_projects", "ix_encounter_set_images_project_id")


def downgrade() -> None:
    conn = op.get_bind()

    for table_name, fk_name, index_name in (
        ("encounter_set_images", "fk_encounter_set_images_project_id_projects", "ix_encounter_set_images_project_id"),
        ("encounter_file_pdfs", "fk_encounter_file_pdfs_project_id_projects", "ix_encounter_file_pdfs_project_id"),
        ("encounter_files", "fk_encounter_files_project_id_projects", "ix_encounter_files_project_id"),
        ("patient_encounters", "fk_patient_encounters_project_id_projects", "ix_patient_encounters_project_id"),
        ("direct_image_uploads", "fk_direct_image_uploads_project_id_projects", "ix_direct_image_uploads_project_id"),
        ("jobs", "fk_jobs_project_id_projects", "ix_jobs_project_id"),
    ):
        if table_name in _table_names(conn):
            if op.get_context().dialect.has_index(conn, table_name, index_name):
                op.drop_index(index_name, table_name=table_name)
            if fk_name in _fk_names(conn, table_name):
                op.drop_constraint(fk_name, table_name, type_="foreignkey")
            if "project_id" in _column_names(conn, table_name):
                op.drop_column(table_name, "project_id")

    for table_name in ("upload_mapping_areas", "upload_mapping_cameras", "upload_mappings", "project_investigators", "projects"):
        if table_name in _table_names(conn):
            op.drop_table(table_name)
