"""Add IITK API EncounterSet synchronization.

Revision ID: c7d8e9f0a1b2
Revises: d8e9f0a1b2c3
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "c7d8e9f0a1b2"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None

SCHEDULE_NAME = "IITK API EncounterSet Sync Hourly IST Business Hours"
TASK_NAME = "celery_tasks.tasks.iitk_tasks.queue_active_iitk_syncs_task"


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "iitk_api_project_configs" not in tables:
        op.create_table(
            "iitk_api_project_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("lab_unit_id", sa.Integer(), nullable=False),
            sa.Column("project_upload_profile_id", sa.Integer(), nullable=False),
            sa.Column("encounter_set_type_id", sa.Integer(), nullable=False),
            sa.Column("camera_id", sa.Integer(), nullable=True),
            sa.Column("base_url", sa.String(length=500), nullable=False),
            sa.Column("api_token_encrypted", sa.Text(), nullable=False),
            sa.Column("secret_salt", sa.String(length=64), nullable=False),
            sa.Column("site_filter", sa.String(length=255), nullable=True),
            sa.Column("sync_from_date", sa.Date(), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["encounter_set_type_id"], ["encounter_set_types.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["lab_unit_id"], ["lab_units.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_upload_profile_id"], ["project_upload_profiles.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", name="uq_iitk_api_project_config_project"),
        )
        op.create_index("ix_iitk_api_project_configs_active", "iitk_api_project_configs", ["active"])
        op.create_index("ix_iitk_api_project_configs_lab_unit_id", "iitk_api_project_configs", ["lab_unit_id"])

    inspector = inspect(op.get_bind())
    if "iitk_api_session_links" not in inspector.get_table_names():
        op.create_table(
            "iitk_api_session_links",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("config_id", sa.Integer(), nullable=False),
            sa.Column("source_session_id", sa.String(length=255), nullable=False),
            sa.Column("patient_encounter_id", sa.Integer(), nullable=False),
            sa.Column("source_status", sa.String(length=16), nullable=False),
            sa.Column("source_image_count", sa.Integer(), nullable=False),
            sa.Column("local_image_count", sa.Integer(), nullable=False),
            sa.Column("inventory_hash", sa.String(length=64), nullable=True),
            sa.Column("source_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.CheckConstraint("source_status IN ('complete','partial')", name="ck_iitk_api_session_status"),
            sa.ForeignKeyConstraint(["config_id"], ["iitk_api_project_configs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["patient_encounter_id"], ["patient_encounters.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("config_id", "source_session_id", name="uq_iitk_api_session_config_source"),
            sa.UniqueConstraint("patient_encounter_id", name="uq_iitk_api_session_patient_encounter"),
        )
        op.create_index("ix_iitk_api_session_links_config_id", "iitk_api_session_links", ["config_id"])
        op.create_index("ix_iitk_api_session_links_config_status", "iitk_api_session_links", ["config_id", "source_status"])
        op.create_index("ix_iitk_api_session_links_source_status", "iitk_api_session_links", ["source_status"])

    if "celery_beat_schedules" in inspect(op.get_bind()).get_table_names():
        op.execute(
            sa.text(
                """
                INSERT INTO celery_beat_schedules
                    (name, task_name, queue, enabled, schedule_type, crontab_hour, crontab_minute,
                     crontab_day_of_week, crontab_day_of_month, crontab_month_of_year,
                     interval_seconds, created_at, updated_at)
                VALUES (:name, :task, 'maintenance', true, 'crontab', '1-12', '30', '*', '*', '*', NULL, NOW(), NOW())
                ON CONFLICT (name) DO UPDATE SET
                    task_name = EXCLUDED.task_name, queue = EXCLUDED.queue, enabled = EXCLUDED.enabled,
                    schedule_type = EXCLUDED.schedule_type, crontab_hour = EXCLUDED.crontab_hour,
                    crontab_minute = EXCLUDED.crontab_minute, interval_seconds = NULL, updated_at = NOW()
                """
            ).bindparams(name=SCHEDULE_NAME, task=TASK_NAME)
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if "celery_beat_schedules" in inspector.get_table_names():
        op.execute(sa.text("DELETE FROM celery_beat_schedules WHERE name = :name").bindparams(name=SCHEDULE_NAME))
    inspector = inspect(op.get_bind())
    if "iitk_api_session_links" in inspector.get_table_names():
        op.drop_table("iitk_api_session_links")
    inspector = inspect(op.get_bind())
    if "iitk_api_project_configs" in inspector.get_table_names():
        op.drop_table("iitk_api_project_configs")
