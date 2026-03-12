"""add image listing v2 beat schedules

Revision ID: 5b7d4c2a1e90
Revises: 4fd8e6f6d2b1
Create Date: 2026-03-12 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5b7d4c2a1e90"
down_revision: Union[str, Sequence[str], None] = "4fd8e6f6d2b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed DB-backed Celery Beat schedules for per-disease image listing v2."""
    op.execute(
        """
        INSERT INTO celery_beat_schedules
            (name, task_name, queue, enabled, schedule_type, crontab_hour, crontab_minute, created_at, updated_at)
        VALUES (
            'Image Listing V2 Ensure Daily',
            'celery_tasks.tasks.mv_tasks.ensure_image_listing_v2_task',
            'maintenance',
            true,
            'crontab',
            '2',
            '0',
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
            interval_seconds = NULL,
            updated_at = NOW();
        """
    )

    op.execute(
        """
        INSERT INTO celery_beat_schedules
            (name, task_name, queue, enabled, schedule_type, interval_seconds, created_at, updated_at)
        VALUES (
            'Image Listing V2 Refresh (30m)',
            'celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task',
            'maintenance',
            true,
            'interval',
            1800,
            NOW(),
            NOW()
        )
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            queue = EXCLUDED.queue,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            interval_seconds = EXCLUDED.interval_seconds,
            crontab_hour = NULL,
            crontab_minute = NULL,
            crontab_day_of_week = NULL,
            crontab_day_of_month = NULL,
            crontab_month_of_year = NULL,
            updated_at = NOW();
        """
    )


def downgrade() -> None:
    """Remove DB-backed Celery Beat schedules for per-disease image listing v2."""
    op.execute(
        """
        DELETE FROM celery_beat_schedules
        WHERE name IN ('Image Listing V2 Ensure Daily', 'Image Listing V2 Refresh (30m)');
        """
    )
