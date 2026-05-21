"""add encounter set asset classification

Revision ID: f9c8e7d6a5b4
Revises: e2b7c9a1d4f6
Create Date: 2026-05-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f9c8e7d6a5b4"
down_revision: Union[str, Sequence[str], None] = "e2b7c9a1d4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def _column_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    return {column["name"] for column in inspect(conn).get_columns(table_name)}


def _constraint_names(conn, table_name: str) -> set[str]:
    if table_name not in _table_names(conn):
        return set()
    inspector = inspect(conn)
    names = {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}
    names.update(fk["name"] for fk in inspector.get_foreign_keys(table_name))
    return names


def _create_index_if_missing(conn, name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if table_name in _table_names(conn) and not op.get_context().dialect.has_index(conn, table_name, name):
        op.create_index(name, table_name, columns, unique=unique)


def _drop_index_if_exists(conn, name: str, table_name: str) -> None:
    if table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if "encounter_set_images" in tables:
        columns = _column_names(conn, "encounter_set_images")
        if "asset_kind" not in columns:
            op.add_column(
                "encounter_set_images",
                sa.Column("asset_kind", sa.String(length=32), nullable=False, server_default="clinical_image"),
            )
        if "creates_task" not in columns:
            op.add_column(
                "encounter_set_images",
                sa.Column("creates_task", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )
        if "is_pii" not in columns:
            op.add_column(
                "encounter_set_images",
                sa.Column("is_pii", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "visible_to_grader" not in columns:
            op.add_column(
                "encounter_set_images",
                sa.Column("visible_to_grader", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )
        op.execute(
            "UPDATE encounter_set_images "
            "SET asset_kind = 'clinical_image', creates_task = true, is_pii = false, visible_to_grader = true "
            "WHERE asset_kind IS NULL OR asset_kind <> 'clinical_image'"
        )
        constraints = _constraint_names(conn, "encounter_set_images")
        if "ck_encounter_set_image_asset_kind" not in constraints:
            op.create_check_constraint(
                "ck_encounter_set_image_asset_kind",
                "encounter_set_images",
                "asset_kind = 'clinical_image'",
            )
        _create_index_if_missing(
            conn,
            "ix_esi_task_evidence",
            "encounter_set_images",
            ["patient_encounter_id", "asset_kind", "creates_task", "visible_to_grader"],
        )

    if "encounter_set_attachments" not in tables:
        op.create_table(
            "encounter_set_attachments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("uuid", sa.String(length=36), nullable=False),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("asset_kind", sa.String(length=32), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=True),
            sa.Column("folder_rel", sa.String(length=512), nullable=True),
            sa.Column("mime_type", sa.String(length=128), nullable=True),
            sa.Column("file_size_bytes", sa.Integer(), nullable=True),
            sa.Column("file_hash", sa.String(length=64), nullable=True),
            sa.Column("is_pii", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("visible_to_grader", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("creates_task", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("upload_profile_id", sa.Integer(), nullable=True),
            sa.Column("hospital_id", sa.Integer(), nullable=True),
            sa.Column("s3_config_id", sa.Integer(), nullable=True),
            sa.Column("s3_object_key", sa.String(length=500), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["patient_encounter_id"], ["patient_encounters.id"], name="fk_esa_patient_encounter_id_patient_encounters", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_esa_project_id_projects", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], name="fk_esa_upload_profile_id_upload_profiles", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"], name="fk_esa_hospital_id_hospitals", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["s3_config_id"], ["s3_configs.id"], name="fk_esa_s3_config_id_s3_configs"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_esa_created_by_user_id_users", ondelete="SET NULL"),
            sa.CheckConstraint("asset_kind IN ('document','pdf','document_image')", name="ck_encounter_set_attachment_asset_kind"),
            sa.CheckConstraint("creates_task = false", name="ck_encounter_set_attachment_never_creates_task"),
            sa.CheckConstraint("stored_filename IS NULL OR position('/' in stored_filename) = 0", name="ck_encounter_set_attachment_stored_filename_no_slash"),
        )

    _create_index_if_missing(conn, "ix_encounter_set_attachments_uuid", "encounter_set_attachments", ["uuid"], unique=True)
    _create_index_if_missing(conn, "ix_encounter_set_attachments_patient_encounter_id", "encounter_set_attachments", ["patient_encounter_id"])
    _create_index_if_missing(conn, "ix_encounter_set_attachments_file_hash", "encounter_set_attachments", ["file_hash"])
    _create_index_if_missing(conn, "ix_encounter_set_attachments_project_id", "encounter_set_attachments", ["project_id"])
    _create_index_if_missing(conn, "ix_encounter_set_attachments_upload_profile_id", "encounter_set_attachments", ["upload_profile_id"])
    _create_index_if_missing(conn, "ix_encounter_set_attachments_hospital_id", "encounter_set_attachments", ["hospital_id"])
    _create_index_if_missing(conn, "ix_encounter_set_attachments_s3_config_id", "encounter_set_attachments", ["s3_config_id"])
    _create_index_if_missing(conn, "ix_encounter_set_attachments_created_by_user_id", "encounter_set_attachments", ["created_by_user_id"])
    _create_index_if_missing(conn, "ix_esa_encounter_kind", "encounter_set_attachments", ["patient_encounter_id", "asset_kind"])
    _create_index_if_missing(conn, "ix_esa_project_kind", "encounter_set_attachments", ["project_id", "asset_kind"])
    _create_index_if_missing(conn, "ix_esa_s3_config_uuid", "encounter_set_attachments", ["s3_config_id", "uuid"])

    if "upload_profile_encounter_set_types" not in _table_names(conn):
        op.create_table(
            "upload_profile_encounter_set_types",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("encounter_set_type_id", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["upload_profile_id"], ["upload_profiles.id"], name="fk_upload_profile_est_upload_profile_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["encounter_set_type_id"], ["encounter_set_types.id"], name="fk_upload_profile_est_encounter_set_type_id", ondelete="CASCADE"),
            sa.UniqueConstraint("upload_profile_id", "encounter_set_type_id", name="uq_upload_profile_encounter_set_type"),
        )
    _create_index_if_missing(conn, "ix_upload_profile_encounter_set_types_upload_profile_id", "upload_profile_encounter_set_types", ["upload_profile_id"])
    _create_index_if_missing(conn, "ix_upload_profile_encounter_set_types_encounter_set_type_id", "upload_profile_encounter_set_types", ["encounter_set_type_id"])
    _create_index_if_missing(conn, "ix_upload_profile_encounter_set_types_active", "upload_profile_encounter_set_types", ["active"])
    _create_index_if_missing(conn, "ix_upload_profile_est_profile_active", "upload_profile_encounter_set_types", ["upload_profile_id", "active"])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)
    if "upload_profile_encounter_set_types" in tables:
        op.drop_table("upload_profile_encounter_set_types")
    if "encounter_set_attachments" in tables:
        op.drop_table("encounter_set_attachments")

    if "encounter_set_images" not in tables:
        return
    _drop_index_if_exists(conn, "ix_esi_task_evidence", "encounter_set_images")
    constraints = _constraint_names(conn, "encounter_set_images")
    if "ck_encounter_set_image_asset_kind" in constraints:
        op.drop_constraint("ck_encounter_set_image_asset_kind", "encounter_set_images", type_="check")
    columns = _column_names(conn, "encounter_set_images")
    for column_name in ("visible_to_grader", "is_pii", "creates_task", "asset_kind"):
        if column_name in columns:
            op.drop_column("encounter_set_images", column_name)
