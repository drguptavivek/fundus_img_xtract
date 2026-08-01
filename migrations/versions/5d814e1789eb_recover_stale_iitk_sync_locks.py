"""recover stale IITK sync locks

Revision ID: 5d814e1789eb
Revises: f0a1b2c3d4e5
Create Date: 2026-08-01 10:52:40.535964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '5d814e1789eb'
down_revision: Union[str, Sequence[str], None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEDULE_NAME = "IITK API Stale Sync Recovery"
TASK_NAME = "celery_tasks.tasks.iitk_tasks.recover_stale_iitk_syncs_task"


def upgrade() -> None:
    if "celery_beat_schedules" not in inspect(op.get_bind()).get_table_names():
        return
    op.execute(
        sa.text(
            """
            INSERT INTO celery_beat_schedules
                (name, task_name, queue, enabled, schedule_type, interval_seconds,
                 crontab_minute, crontab_hour, crontab_day_of_week,
                 crontab_day_of_month, crontab_month_of_year, created_at, updated_at)
            VALUES (:name, :task, 'maintenance', true, 'interval', 300,
                    NULL, NULL, NULL, NULL, NULL, NOW(), NOW())
            ON CONFLICT (name) DO UPDATE SET
                task_name = EXCLUDED.task_name,
                queue = EXCLUDED.queue,
                enabled = EXCLUDED.enabled,
                schedule_type = EXCLUDED.schedule_type,
                interval_seconds = EXCLUDED.interval_seconds,
                crontab_minute = NULL,
                crontab_hour = NULL,
                crontab_day_of_week = NULL,
                crontab_day_of_month = NULL,
                crontab_month_of_year = NULL,
                updated_at = NOW()
            """
        ).bindparams(name=SCHEDULE_NAME, task=TASK_NAME)
    )


def downgrade() -> None:
    if "celery_beat_schedules" not in inspect(op.get_bind()).get_table_names():
        return
    op.execute(sa.text("DELETE FROM celery_beat_schedules WHERE name = :name").bindparams(name=SCHEDULE_NAME))
