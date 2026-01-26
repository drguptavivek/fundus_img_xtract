"""Add celery beat schedules table."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c7f4a8e3d1b2"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "celery_beat_schedules" not in inspector.get_table_names():
        op.create_table(
            "celery_beat_schedules",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("task_name", sa.String(length=255), nullable=False),
            sa.Column("queue", sa.String(length=64), nullable=True),
            sa.Column("schedule_type", sa.String(length=16), nullable=False, server_default="interval"),
            sa.Column("interval_seconds", sa.Integer(), nullable=True),
            sa.Column("crontab_minute", sa.String(length=64), nullable=True),
            sa.Column("crontab_hour", sa.String(length=64), nullable=True),
            sa.Column("crontab_day_of_week", sa.String(length=64), nullable=True),
            sa.Column("crontab_day_of_month", sa.String(length=64), nullable=True),
            sa.Column("crontab_month_of_year", sa.String(length=64), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("hospital_id", sa.Integer(), sa.ForeignKey("hospitals.id"), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.CheckConstraint(
                "schedule_type IN ('interval','crontab')",
                name="ck_celery_beat_schedule_type",
            ),
            sa.CheckConstraint(
                "(schedule_type = 'interval' AND interval_seconds IS NOT NULL) "
                "OR (schedule_type = 'crontab' AND interval_seconds IS NULL)",
                name="ck_celery_beat_schedule_interval_consistency",
            ),
            sa.UniqueConstraint("name", name="uq_celery_beat_schedules_name"),
        )

    if not inspector.has_index("celery_beat_schedules", "ix_celery_beat_enabled_type"):
        op.create_index(
            "ix_celery_beat_enabled_type",
            "celery_beat_schedules",
            ["enabled", "schedule_type"],
        )
    if not inspector.has_index("celery_beat_schedules", "ix_celery_beat_schedules_user_id"):
        op.create_index(
            "ix_celery_beat_schedules_user_id",
            "celery_beat_schedules",
            ["user_id"],
        )
    if not inspector.has_index("celery_beat_schedules", "ix_celery_beat_schedules_hospital_id"):
        op.create_index(
            "ix_celery_beat_schedules_hospital_id",
            "celery_beat_schedules",
            ["hospital_id"],
        )
    if not inspector.has_index("celery_beat_schedules", "ix_celery_beat_schedules_created_by_id"):
        op.create_index(
            "ix_celery_beat_schedules_created_by_id",
            "celery_beat_schedules",
            ["created_by_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    if "celery_beat_schedules" in inspector.get_table_names():
        if inspector.has_index("celery_beat_schedules", "ix_celery_beat_schedules_created_by_id"):
            op.drop_index("ix_celery_beat_schedules_created_by_id", table_name="celery_beat_schedules")
        if inspector.has_index("celery_beat_schedules", "ix_celery_beat_schedules_hospital_id"):
            op.drop_index("ix_celery_beat_schedules_hospital_id", table_name="celery_beat_schedules")
        if inspector.has_index("celery_beat_schedules", "ix_celery_beat_schedules_user_id"):
            op.drop_index("ix_celery_beat_schedules_user_id", table_name="celery_beat_schedules")
        if inspector.has_index("celery_beat_schedules", "ix_celery_beat_enabled_type"):
            op.drop_index("ix_celery_beat_enabled_type", table_name="celery_beat_schedules")
        op.drop_table("celery_beat_schedules")
