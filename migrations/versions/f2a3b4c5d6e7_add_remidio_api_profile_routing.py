"""add remidio api profile routing

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UPLOAD_PROFILES = "upload_profiles"
SOURCE_RULES = "remidio_api_source_rules"
BINDINGS = "project_upload_profile_remidio_api_bindings"
EXAM_ENCOUNTERS = "remidio_api_exam_encounters"
PATIENT_ENCOUNTERS = "patient_encounters"
ENCOUNTER_SET_IMAGES = "encounter_set_images"
ENCOUNTER_SET_ATTACHMENTS = "encounter_set_attachments"
REMIDIO_IMAGES = "remidio_images"
REMIDIO_REPORTS = "remidio_reports"


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
    names.update(constraint["name"] for constraint in inspector.get_unique_constraints(table_name))
    names.update(constraint["name"] for constraint in inspector.get_foreign_keys(table_name))
    return names


def _index_exists(conn, table_name: str, name: str) -> bool:
    return table_name in _table_names(conn) and op.get_context().dialect.has_index(conn, table_name, name)


def _drop_index_if_exists(conn, table_name: str, name: str) -> None:
    if _index_exists(conn, table_name, name):
        op.drop_index(name, table_name=table_name)


def _drop_constraint_if_exists(conn, table_name: str, name: str, constraint_type: str) -> None:
    if table_name in _table_names(conn) and name in _constraint_names(conn, table_name):
        op.drop_constraint(name, table_name, type_=constraint_type)


def upgrade() -> None:
    conn = op.get_bind()
    tables = _table_names(conn)

    if UPLOAD_PROFILES in tables and "automated_remidio_populated" not in _column_names(conn, UPLOAD_PROFILES):
        op.add_column(
            UPLOAD_PROFILES,
            sa.Column("automated_remidio_populated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if PATIENT_ENCOUNTERS in tables and "metadata_json" not in _column_names(conn, PATIENT_ENCOUNTERS):
        op.add_column(PATIENT_ENCOUNTERS, sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if ENCOUNTER_SET_IMAGES in tables and "metadata_json" not in _column_names(conn, ENCOUNTER_SET_IMAGES):
        op.add_column(ENCOUNTER_SET_IMAGES, sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if REMIDIO_IMAGES in tables:
        if "encounter_set_image_id" not in _column_names(conn, REMIDIO_IMAGES):
            op.add_column(REMIDIO_IMAGES, sa.Column("encounter_set_image_id", sa.Integer(), nullable=True))
        if ENCOUNTER_SET_IMAGES in tables and "fk_remidio_images_encounter_set_image" not in _constraint_names(conn, REMIDIO_IMAGES):
            op.create_foreign_key(
                "fk_remidio_images_encounter_set_image",
                REMIDIO_IMAGES,
                ENCOUNTER_SET_IMAGES,
                ["encounter_set_image_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if not _index_exists(conn, REMIDIO_IMAGES, "ix_remidio_images_encounter_set_image_id"):
            op.create_index("ix_remidio_images_encounter_set_image_id", REMIDIO_IMAGES, ["encounter_set_image_id"])
    if REMIDIO_REPORTS in tables:
        if "encounter_set_attachment_id" not in _column_names(conn, REMIDIO_REPORTS):
            op.add_column(REMIDIO_REPORTS, sa.Column("encounter_set_attachment_id", sa.Integer(), nullable=True))
        if ENCOUNTER_SET_ATTACHMENTS in tables and "fk_remidio_reports_encounter_set_attachment" not in _constraint_names(conn, REMIDIO_REPORTS):
            op.create_foreign_key(
                "fk_remidio_reports_encounter_set_attachment",
                REMIDIO_REPORTS,
                ENCOUNTER_SET_ATTACHMENTS,
                ["encounter_set_attachment_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if not _index_exists(conn, REMIDIO_REPORTS, "ix_remidio_reports_encounter_set_attachment_id"):
            op.create_index("ix_remidio_reports_encounter_set_attachment_id", REMIDIO_REPORTS, ["encounter_set_attachment_id"])
    if ENCOUNTER_SET_IMAGES in tables:
        _drop_constraint_if_exists(conn, ENCOUNTER_SET_IMAGES, "ck_encounter_set_image_position_range", "check")
        if "ck_encounter_set_image_position_positive" not in _constraint_names(conn, ENCOUNTER_SET_IMAGES):
            op.create_check_constraint(
                "ck_encounter_set_image_position_positive",
                ENCOUNTER_SET_IMAGES,
                "spatial_position >= 1",
            )

    if SOURCE_RULES not in tables:
        op.create_table(
            SOURCE_RULES,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_connection_id", sa.Integer(), nullable=False),
            sa.Column("remidio_site_id", sa.Integer(), nullable=True),
            sa.Column("site_custom_identifier", sa.String(length=255), nullable=False),
            sa.Column("remidio_device_type", sa.String(length=64), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["remidio_connection_id"],
                ["remidio_connections.id"],
                name="fk_remidio_api_source_rule_connection",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["remidio_site_id"],
                ["remidio_sites.id"],
                name="fk_remidio_api_source_rule_site",
                ondelete="SET NULL",
            ),
        )
    if not _index_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rules_remidio_connection_id"):
        op.create_index("ix_remidio_api_source_rules_remidio_connection_id", SOURCE_RULES, ["remidio_connection_id"])
    if not _index_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rules_remidio_site_id"):
        op.create_index("ix_remidio_api_source_rules_remidio_site_id", SOURCE_RULES, ["remidio_site_id"])
    if not _index_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rules_active"):
        op.create_index("ix_remidio_api_source_rules_active", SOURCE_RULES, ["active"])
    if not _index_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rule_lookup"):
        op.create_index(
            "ix_remidio_api_source_rule_lookup",
            SOURCE_RULES,
            ["remidio_connection_id", "site_custom_identifier", "remidio_device_type", "active"],
        )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_remidio_api_source_rule_active
        ON remidio_api_source_rules (remidio_connection_id, site_custom_identifier, remidio_device_type)
        WHERE active IS TRUE
        """
    )

    if BINDINGS not in tables:
        op.create_table(
            BINDINGS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("remidio_api_source_rule_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("camera_id", sa.Integer(), nullable=False),
            sa.Column("active_from_date", sa.Date(), nullable=False),
            sa.Column("active_to_date", sa.Date(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(
                ["project_upload_profile_id"],
                ["project_upload_profiles.id"],
                name="fk_pup_remidio_api_binding_project_profile",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["remidio_api_source_rule_id"],
                ["remidio_api_source_rules.id"],
                name="fk_pup_remidio_api_binding_source_rule",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], name="fk_pup_remidio_api_binding_lab_unit", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name="fk_pup_remidio_api_binding_camera", ondelete="RESTRICT"),
            sa.CheckConstraint(
                "active_to_date IS NULL OR active_to_date >= active_from_date",
                name="ck_pup_remidio_api_binding_date_order",
            ),
        )
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_project_profile"):
        op.create_index(
            "ix_pup_remidio_api_binding_project_profile",
            BINDINGS,
            ["project_upload_profile_id"],
        )
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_source_rule"):
        op.create_index(
            "ix_pup_remidio_api_binding_source_rule",
            BINDINGS,
            ["remidio_api_source_rule_id"],
        )
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_lab_unit"):
        op.create_index("ix_pup_remidio_api_binding_lab_unit", BINDINGS, ["lab_unit_id"])
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_camera"):
        op.create_index("ix_pup_remidio_api_binding_camera", BINDINGS, ["camera_id"])
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_active_flag"):
        op.create_index("ix_pup_remidio_api_binding_active_flag", BINDINGS, ["active"])
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_active"):
        op.create_index("ix_pup_remidio_api_binding_active", BINDINGS, ["project_upload_profile_id", "active"])
    if not _index_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_source_active"):
        op.create_index("ix_pup_remidio_api_binding_source_active", BINDINGS, ["remidio_api_source_rule_id", "active"])

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'excl_pup_remidio_api_binding_date_overlap'
            ) THEN
                ALTER TABLE project_upload_profile_remidio_api_bindings
                ADD CONSTRAINT excl_pup_remidio_api_binding_date_overlap
                EXCLUDE USING gist (
                    remidio_api_source_rule_id WITH =,
                    daterange(active_from_date, COALESCE(active_to_date, 'infinity'::date), '[]') WITH &&
                )
                WHERE (active IS TRUE);
            END IF;
        END $$;
        """
    )

    if EXAM_ENCOUNTERS not in _table_names(conn):
        op.create_table(
            EXAM_ENCOUNTERS,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("remidio_exam_id", sa.Integer(), nullable=False),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("project_upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("remidio_api_binding_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["remidio_exam_id"], ["remidio_exams.id"], name="fk_remidio_api_exam_encounter_exam", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["patient_encounter_id"],
                ["patient_encounters.id"],
                name="fk_remidio_api_exam_encounter_patient_encounter",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["project_upload_profile_id"],
                ["project_upload_profiles.id"],
                name="fk_remidio_api_exam_encounter_project_profile",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["remidio_api_binding_id"],
                ["project_upload_profile_remidio_api_bindings.id"],
                name="fk_remidio_api_exam_encounter_binding",
                ondelete="RESTRICT",
            ),
        )
    if not _index_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_remidio_exam_id"):
        op.create_index("ix_remidio_api_exam_encounters_remidio_exam_id", EXAM_ENCOUNTERS, ["remidio_exam_id"])
    if not _index_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_patient_encounter_id"):
        op.create_index("ix_remidio_api_exam_encounters_patient_encounter_id", EXAM_ENCOUNTERS, ["patient_encounter_id"])
    if not _index_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_project_upload_profile_id"):
        op.create_index("ix_remidio_api_exam_encounters_project_upload_profile_id", EXAM_ENCOUNTERS, ["project_upload_profile_id"])
    if not _index_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_remidio_api_binding_id"):
        op.create_index("ix_remidio_api_exam_encounters_remidio_api_binding_id", EXAM_ENCOUNTERS, ["remidio_api_binding_id"])
    if not _index_exists(conn, EXAM_ENCOUNTERS, "uq_remidio_api_exam_encounter_route"):
        op.create_index(
            "uq_remidio_api_exam_encounter_route",
            EXAM_ENCOUNTERS,
            ["remidio_exam_id", "project_upload_profile_id", "remidio_api_binding_id"],
            unique=True,
        )
    if not _index_exists(conn, EXAM_ENCOUNTERS, "uq_remidio_api_exam_encounter_patient"):
        op.create_index("uq_remidio_api_exam_encounter_patient", EXAM_ENCOUNTERS, ["patient_encounter_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()

    _drop_index_if_exists(conn, EXAM_ENCOUNTERS, "uq_remidio_api_exam_encounter_patient")
    _drop_index_if_exists(conn, EXAM_ENCOUNTERS, "uq_remidio_api_exam_encounter_route")
    _drop_index_if_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_remidio_api_binding_id")
    _drop_index_if_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_project_upload_profile_id")
    _drop_index_if_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_patient_encounter_id")
    _drop_index_if_exists(conn, EXAM_ENCOUNTERS, "ix_remidio_api_exam_encounters_remidio_exam_id")
    if EXAM_ENCOUNTERS in _table_names(conn):
        op.drop_table(EXAM_ENCOUNTERS)

    if BINDINGS in _table_names(conn):
        op.execute("ALTER TABLE project_upload_profile_remidio_api_bindings DROP CONSTRAINT IF EXISTS excl_pup_remidio_api_binding_date_overlap")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_source_active")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_active")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_active_flag")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_camera")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_lab_unit")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_source_rule")
    _drop_index_if_exists(conn, BINDINGS, "ix_pup_remidio_api_binding_project_profile")
    if BINDINGS in _table_names(conn):
        op.drop_table(BINDINGS)

    _drop_index_if_exists(conn, SOURCE_RULES, "uq_remidio_api_source_rule_active")
    _drop_index_if_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rule_lookup")
    _drop_index_if_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rules_active")
    _drop_index_if_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rules_remidio_site_id")
    _drop_index_if_exists(conn, SOURCE_RULES, "ix_remidio_api_source_rules_remidio_connection_id")
    if SOURCE_RULES in _table_names(conn):
        op.drop_table(SOURCE_RULES)

    if UPLOAD_PROFILES in _table_names(conn) and "automated_remidio_populated" in _column_names(conn, UPLOAD_PROFILES):
        op.drop_column(UPLOAD_PROFILES, "automated_remidio_populated")
    if ENCOUNTER_SET_IMAGES in _table_names(conn):
        _drop_constraint_if_exists(conn, ENCOUNTER_SET_IMAGES, "ck_encounter_set_image_position_positive", "check")
        if "ck_encounter_set_image_position_range" not in _constraint_names(conn, ENCOUNTER_SET_IMAGES):
            op.create_check_constraint(
                "ck_encounter_set_image_position_range",
                ENCOUNTER_SET_IMAGES,
                "spatial_position >= 1 AND spatial_position <= 9",
            )
        if "metadata_json" in _column_names(conn, ENCOUNTER_SET_IMAGES):
            op.drop_column(ENCOUNTER_SET_IMAGES, "metadata_json")
    if REMIDIO_REPORTS in _table_names(conn) and "encounter_set_attachment_id" in _column_names(conn, REMIDIO_REPORTS):
        _drop_index_if_exists(conn, REMIDIO_REPORTS, "ix_remidio_reports_encounter_set_attachment_id")
        _drop_constraint_if_exists(conn, REMIDIO_REPORTS, "fk_remidio_reports_encounter_set_attachment", "foreignkey")
        op.drop_column(REMIDIO_REPORTS, "encounter_set_attachment_id")
    if REMIDIO_IMAGES in _table_names(conn) and "encounter_set_image_id" in _column_names(conn, REMIDIO_IMAGES):
        _drop_index_if_exists(conn, REMIDIO_IMAGES, "ix_remidio_images_encounter_set_image_id")
        _drop_constraint_if_exists(conn, REMIDIO_IMAGES, "fk_remidio_images_encounter_set_image", "foreignkey")
        op.drop_column(REMIDIO_IMAGES, "encounter_set_image_id")
    if PATIENT_ENCOUNTERS in _table_names(conn) and "metadata_json" in _column_names(conn, PATIENT_ENCOUNTERS):
        op.drop_column(PATIENT_ENCOUNTERS, "metadata_json")
