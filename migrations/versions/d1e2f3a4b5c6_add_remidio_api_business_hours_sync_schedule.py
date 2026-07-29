"""Add Remidio API business-hours auto sync schedule.

Revision ID: d1e2f3a4b5c6
Revises: c9d8e7f6a5b4
Create Date: 2026-07-29
"""

from alembic import op
from sqlalchemy import inspect


revision = "d1e2f3a4b5c6"
down_revision = "c9d8e7f6a5b4"
branch_labels = None
depends_on = None


SCHEDULE_TABLE = "celery_beat_schedules"
SCHEDULE_NAME = "Remidio API Prospective Sync Hourly IST Business Hours"
TASK_NAME = "celery_tasks.tasks.remidio_tasks.queue_remidio_api_prospective_project_syncs_task"


def _has_schedule_table() -> bool:
    return SCHEDULE_TABLE in inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_schedule_table():
        return

    op.execute(
        f"""
        INSERT INTO {SCHEDULE_TABLE}
            (
                name,
                task_name,
                queue,
                enabled,
                schedule_type,
                crontab_hour,
                crontab_minute,
                crontab_day_of_week,
                crontab_day_of_month,
                crontab_month_of_year,
                interval_seconds,
                created_at,
                updated_at
            )
        VALUES (
            '{SCHEDULE_NAME}',
            '{TASK_NAME}',
            'maintenance',
            true,
            'crontab',
            '2-13',
            '30',
            '*',
            '*',
            '*',
            NULL,
            NOW(),
            NOW()
        )
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            queue = EXCLUDED.queue,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            crontab_hour = EXCLUDED.crontab_hour,
            crontab_minute = EXCLUDED.crontab_minute,
            crontab_day_of_week = EXCLUDED.crontab_day_of_week,
            crontab_day_of_month = EXCLUDED.crontab_day_of_month,
            crontab_month_of_year = EXCLUDED.crontab_month_of_year,
            interval_seconds = NULL,
            updated_at = NOW();
        """
    )


def downgrade():
    if not _has_schedule_table():
        return

    op.execute(
        f"""
        DELETE FROM {SCHEDULE_TABLE}
        WHERE name = '{SCHEDULE_NAME}';
        """
    )
