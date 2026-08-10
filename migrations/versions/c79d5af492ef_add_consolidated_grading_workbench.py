"""add consolidated grading workbench

Revision ID: c79d5af492ef
Revises: 531cf24d8a10
Create Date: 2026-08-10 14:04:54.651203
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c79d5af492ef"
down_revision: Union[str, Sequence[str], None] = "531cf24d8a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {item["name"] for item in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if table_name not in _tables():
        return set()
    return {item["name"] for item in _inspector().get_indexes(table_name)}


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False, where: str | None = None) -> None:
    if name in _indexes(table):
        return
    kwargs = {"postgresql_where": sa.text(where)} if where else {}
    op.create_index(name, table, columns, unique=unique, **kwargs)


def _backfill_source_profiles() -> None:
    """Backfill only lineage that can be proven from one authoritative parent."""
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE grading_tasks AS task
        SET source_upload_profile_id = encounter.upload_profile_id
        FROM encounter_files AS image
        JOIN patient_encounters AS encounter
          ON encounter.id = image.patient_encounter_id
        WHERE task.source_upload_profile_id IS NULL
          AND task.encounter_file_id = image.id
          AND encounter.upload_profile_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE grading_tasks AS task
        SET source_upload_profile_id = encounter.upload_profile_id
        FROM encounter_set_images AS image
        JOIN patient_encounters AS encounter
          ON encounter.id = image.patient_encounter_id
        WHERE task.source_upload_profile_id IS NULL
          AND task.encounter_set_image_id = image.id
          AND encounter.upload_profile_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE grading_tasks AS task
        SET source_upload_profile_id = encounter.upload_profile_id
        FROM patient_encounters AS encounter
        WHERE task.source_upload_profile_id IS NULL
          AND task.patient_encounter_id = encounter.id
          AND encounter.upload_profile_id IS NOT NULL
    """))
    if {"job_items", "jobs"}.issubset(_tables()):
        bind.execute(sa.text("""
            WITH deterministic_profile AS (
                SELECT item.task_id, min(job.upload_profile_id) AS upload_profile_id
                FROM job_items AS item
                JOIN jobs AS job ON job.id = item.job_id
                WHERE item.task_id IS NOT NULL
                  AND job.upload_profile_id IS NOT NULL
                GROUP BY item.task_id
                HAVING count(DISTINCT job.upload_profile_id) = 1
            )
            UPDATE grading_tasks AS task
            SET source_upload_profile_id = source.upload_profile_id
            FROM deterministic_profile AS source
            WHERE task.source_upload_profile_id IS NULL
              AND task.direct_image_upload_id IS NOT NULL
              AND task.id = source.task_id
        """))


def upgrade() -> None:
    if "source_upload_profile_id" not in _columns("grading_tasks"):
        op.add_column("grading_tasks", sa.Column("source_upload_profile_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_grading_tasks_source_upload_profile",
            "grading_tasks",
            "upload_profiles",
            ["source_upload_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
    _create_index(
        "ix_grading_tasks_source_upload_profile_id",
        "grading_tasks",
        ["source_upload_profile_id"],
    )
    _backfill_source_profiles()

    if "grading_workbench_sessions" not in _tables():
        op.create_table(
            "grading_workbench_sessions",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role_slot", sa.String(16), nullable=False),
            sa.Column("workflow", sa.String(32), nullable=False),
            sa.Column("status", sa.String(16), server_default="active", nullable=False),
            sa.Column("root_task_id", sa.Integer(), nullable=True),
            sa.Column("encounter_set_package_id", sa.Integer(), nullable=True),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("token_generation", sa.Integer(), server_default="1", nullable=False),
            sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("queue_request_json", JSONB, nullable=True),
            sa.Column("configuration_snapshot_json", JSONB, nullable=False),
            sa.Column("configuration_fingerprint", sa.String(64), nullable=False),
            sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("close_reason", sa.String(64), nullable=True),
            sa.Column("next_session_id", sa.BigInteger(), nullable=True),
            sa.CheckConstraint("role_slot IN ('resident','resident2','arbitrator','review','regrade_adj')", name="ck_gws_role_slot"),
            sa.CheckConstraint("status IN ('active','completed','released','expired','invalidated')", name="ck_gws_status"),
            sa.CheckConstraint("token_generation >= 1", name="ck_gws_token_generation"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["root_task_id"], ["grading_tasks.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["encounter_set_package_id"], ["encounter_set_grading_packages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["next_session_id"], ["grading_workbench_sessions.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid", name="uq_grading_workbench_sessions_uuid"),
        )
    _create_index("ix_gws_uuid", "grading_workbench_sessions", ["uuid"], unique=True)
    _create_index("ix_gws_user", "grading_workbench_sessions", ["user_id"])
    _create_index("ix_gws_active_expiry", "grading_workbench_sessions", ["status", "idle_expires_at", "absolute_expires_at"])
    _create_index("uq_gws_active_user_slot", "grading_workbench_sessions", ["user_id", "role_slot"], unique=True, where="status = 'active'")

    if "grading_workbench_session_targets" not in _tables():
        op.create_table(
            "grading_workbench_session_targets",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.BigInteger(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("role_slot", sa.String(16), nullable=False),
            sa.Column("target_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("target_purpose", sa.String(24), server_default="editable", nullable=False),
            sa.Column("acquired_task_state", sa.String(24), nullable=False),
            sa.Column("acquired_grade_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("release_reason", sa.String(64), nullable=True),
            sa.CheckConstraint("target_purpose IN ('editable','evidence','followup')", name="ck_gwst_purpose"),
            sa.ForeignKeyConstraint(["session_id"], ["grading_workbench_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["grading_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("session_id", "task_id", "role_slot", name="uq_gwst_session_task_slot"),
        )
    _create_index("ix_gwst_session", "grading_workbench_session_targets", ["session_id"])
    _create_index("ix_gwst_task", "grading_workbench_session_targets", ["task_id"])
    _create_index(
        "uq_gwst_active_task_slot",
        "grading_workbench_session_targets",
        ["task_id", "role_slot"],
        unique=True,
        where="released_at IS NULL AND target_purpose = 'editable'",
    )

    if "grading_submission_events" not in _tables():
        op.create_table(
            "grading_submission_events",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=False),
            sa.Column("role_slot", sa.String(16), nullable=False),
            sa.Column("workflow", sa.String(32), nullable=False),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("outcome", sa.String(16), nullable=False),
            sa.Column("result_code", sa.String(64), nullable=False),
            sa.Column("session_id", sa.BigInteger(), nullable=True),
            sa.Column("root_task_id", sa.Integer(), nullable=True),
            sa.Column("encounter_set_package_id", sa.Integer(), nullable=True),
            sa.Column("project_id", sa.Integer(), nullable=True),
            sa.Column("lab_unit_id", sa.Integer(), nullable=True),
            sa.Column("source_profile_id", sa.Integer(), nullable=True),
            sa.Column("source_lineage", sa.String(32), nullable=True),
            sa.Column("configuration_fingerprint", sa.String(64), nullable=True),
            sa.Column("policy_revisions_json", JSONB, nullable=True),
            sa.Column("idempotency_key", sa.String(64), nullable=True),
            sa.Column("correlation_id", sa.String(64), nullable=True),
            sa.Column("diagnostic_metadata_json", JSONB, nullable=True),
            sa.Column("specialized_record_type", sa.String(64), nullable=True),
            sa.Column("specialized_record_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("outcome IN ('accepted','rejected','conflict')", name="ck_gse_outcome"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["session_id"], ["grading_workbench_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["root_task_id"], ["grading_tasks.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["encounter_set_package_id"], ["encounter_set_grading_packages.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_profile_id"], ["upload_profiles.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid", name="uq_grading_submission_events_uuid"),
            sa.UniqueConstraint("session_id", "idempotency_key", name="uq_gse_session_idempotency"),
        )
    _create_index("ix_gse_uuid", "grading_submission_events", ["uuid"], unique=True)
    _create_index("ix_gse_actor_created", "grading_submission_events", ["actor_user_id", "created_at"])
    _create_index("ix_gse_session", "grading_submission_events", ["session_id"])

    if "grading_submission_event_items" not in _tables():
        op.create_table(
            "grading_submission_event_items",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.BigInteger(), nullable=False),
            sa.Column("task_id", sa.Integer(), nullable=False),
            sa.Column("grade_id", sa.Integer(), nullable=True),
            sa.Column("disease_id", sa.Integer(), nullable=False),
            sa.Column("target_level", sa.String(24), nullable=False),
            sa.Column("grade_revision", sa.Integer(), server_default="1", nullable=False),
            sa.Column("before_json", JSONB, nullable=True),
            sa.Column("after_json", JSONB, nullable=False),
            sa.Column("annotation_set_uuid", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("target_level IN ('image','encounter')", name="ck_gsei_target_level"),
            sa.CheckConstraint("grade_revision >= 1", name="ck_gsei_grade_revision"),
            sa.ForeignKeyConstraint(["event_id"], ["grading_submission_events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["grading_tasks.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["disease_id"], ["diseases.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("event_id", "task_id", name="uq_gsei_event_task"),
        )
    _create_index("ix_gsei_event", "grading_submission_event_items", ["event_id"])
    _create_index("ix_gsei_task", "grading_submission_event_items", ["task_id"])

    if "annotation_sets" not in _tables():
        op.create_table(
            "annotation_sets",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("grade_id", sa.Integer(), nullable=True),
            sa.Column("intra_rater_grade_id", sa.Integer(), nullable=True),
            sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
            sa.Column("policy_source", sa.String(32), nullable=False),
            sa.Column("policy_revision", sa.Integer(), nullable=False),
            sa.Column("source_image_width", sa.Integer(), nullable=True),
            sa.Column("source_image_height", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("(grade_id IS NOT NULL AND intra_rater_grade_id IS NULL) OR (grade_id IS NULL AND intra_rater_grade_id IS NOT NULL)", name="ck_annotation_set_single_owner"),
            sa.CheckConstraint("schema_version >= 1", name="ck_annotation_set_schema_version"),
            sa.CheckConstraint("policy_revision >= 0", name="ck_annotation_set_policy_revision"),
            sa.ForeignKeyConstraint(["grade_id"], ["grades.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["intra_rater_grade_id"], ["intra_rater_grades.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid", name="uq_annotation_sets_uuid"),
            sa.UniqueConstraint("grade_id", name="uq_annotation_sets_grade"),
            sa.UniqueConstraint("intra_rater_grade_id", name="uq_annotation_sets_intra_grade"),
        )
    _create_index("ix_annotation_sets_uuid", "annotation_sets", ["uuid"], unique=True)

    if "annotation_instances" not in _tables():
        op.create_table(
            "annotation_instances",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("annotation_set_id", sa.BigInteger(), nullable=False),
            sa.Column("image_uuid", sa.String(36), nullable=False),
            sa.Column("class_source", sa.String(32), nullable=False),
            sa.Column("grading_feature_id", sa.Integer(), nullable=True),
            sa.Column("project_class_id", sa.Integer(), nullable=True),
            sa.Column("class_key_snapshot", sa.String(128), nullable=False),
            sa.Column("class_label_snapshot", sa.String(255), nullable=False),
            sa.Column("policy_revision", sa.Integer(), nullable=False),
            sa.Column("geometry_type", sa.String(24), nullable=False),
            sa.Column("geometry_json", JSONB, nullable=False),
            sa.Column("bbox_x", sa.Float(), nullable=True),
            sa.Column("bbox_y", sa.Float(), nullable=True),
            sa.Column("bbox_w", sa.Float(), nullable=True),
            sa.Column("bbox_h", sa.Float(), nullable=True),
            sa.Column("instance_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("class_source IN ('grading_feature','project_class')", name="ck_annotation_instance_class_source"),
            sa.CheckConstraint("(class_source = 'grading_feature' AND grading_feature_id IS NOT NULL AND project_class_id IS NULL) OR (class_source = 'project_class' AND grading_feature_id IS NULL AND project_class_id IS NOT NULL)", name="ck_annotation_instance_class_identity"),
            sa.CheckConstraint("geometry_type IN ('none','box','rect','polygon','brush_mask','ellipse','pyramid')", name="ck_annotation_instance_geometry_type"),
            sa.CheckConstraint("policy_revision >= 0", name="ck_annotation_instance_policy_revision"),
            sa.CheckConstraint("instance_order >= 0", name="ck_annotation_instance_order"),
            sa.ForeignKeyConstraint(["annotation_set_id"], ["annotation_sets.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["grading_feature_id"], ["gradings_features.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["project_class_id"], ["project_annotation_classes.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid", name="uq_annotation_instances_uuid"),
        )
    _create_index("ix_annotation_instances_uuid", "annotation_instances", ["uuid"], unique=True)
    _create_index("ix_annotation_instance_set_order", "annotation_instances", ["annotation_set_id", "instance_order"])
    _create_index("ix_annotation_instances_image_uuid", "annotation_instances", ["image_uuid"])

    if "annotation_mask_tiles" not in _tables():
        op.create_table(
            "annotation_mask_tiles",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("annotation_instance_id", sa.BigInteger(), nullable=False),
            sa.Column("tile_x", sa.Integer(), nullable=False),
            sa.Column("tile_y", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("png_bytes", sa.LargeBinary(), nullable=False),
            sa.Column("checksum", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("tile_x >= 0 AND tile_y >= 0", name="ck_annotation_mask_tile_coordinates"),
            sa.CheckConstraint("width BETWEEN 1 AND 256 AND height BETWEEN 1 AND 256", name="ck_annotation_mask_tile_dimensions"),
            sa.ForeignKeyConstraint(["annotation_instance_id"], ["annotation_instances.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("annotation_instance_id", "tile_x", "tile_y", name="uq_annotation_mask_tile_position"),
        )
    _create_index("ix_annotation_mask_tiles_instance", "annotation_mask_tiles", ["annotation_instance_id"])


def downgrade() -> None:
    for table_name in (
        "annotation_mask_tiles",
        "annotation_instances",
        "annotation_sets",
        "grading_submission_event_items",
        "grading_submission_events",
        "grading_workbench_session_targets",
        "grading_workbench_sessions",
    ):
        if table_name in _tables():
            op.drop_table(table_name)

    if "source_upload_profile_id" in _columns("grading_tasks"):
        if "ix_grading_tasks_source_upload_profile_id" in _indexes("grading_tasks"):
            op.drop_index("ix_grading_tasks_source_upload_profile_id", table_name="grading_tasks")
        foreign_keys = {
            item.get("name")
            for item in _inspector().get_foreign_keys("grading_tasks")
            if item.get("constrained_columns") == ["source_upload_profile_id"]
        }
        for name in foreign_keys:
            if name:
                op.drop_constraint(name, "grading_tasks", type_="foreignkey")
        op.drop_column("grading_tasks", "source_upload_profile_id")
