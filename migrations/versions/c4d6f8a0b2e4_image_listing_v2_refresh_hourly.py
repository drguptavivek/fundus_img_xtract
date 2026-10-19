"""refresh materialized views hourly instead of every 30 minutes

Revision ID: c4d6f8a0b2e4
Revises: a1c3e5f7b9d2
Create Date: 2026-10-19 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4d6f8a0b2e4"
down_revision: Union[str, Sequence[str], None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMAGE_LISTING_TASK = "celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task"
PIVOT_TASK = "celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task"


def _set_interval(task: str, old_name: str, new_name: str, seconds: int) -> None:
    """Rename and re-time the refresh schedule; insert it when neither name exists."""
    op.execute(
        f"""
        UPDATE celery_beat_schedules
        SET name = '{new_name}', interval_seconds = {seconds}, updated_at = NOW()
        WHERE name = '{old_name}'
          AND NOT EXISTS (SELECT 1 FROM celery_beat_schedules WHERE name = '{new_name}');
        """
    )
    op.execute(
        f"""
        INSERT INTO celery_beat_schedules
            (name, task_name, queue, enabled, schedule_type, interval_seconds, created_at, updated_at)
        VALUES ('{new_name}', '{task}', 'maintenance', true, 'interval', {seconds}, NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            interval_seconds = EXCLUDED.interval_seconds,
            updated_at = NOW();
        """
    )


def upgrade() -> None:
    _set_interval(IMAGE_LISTING_TASK, "Image Listing V2 Refresh (30m)", "Image Listing V2 Refresh (60m)", 3600)
    _set_interval(PIVOT_TASK, "Materialized View Refresh (30m)", "Materialized View Refresh (60m)", 3600)


def downgrade() -> None:
    _set_interval(IMAGE_LISTING_TASK, "Image Listing V2 Refresh (60m)", "Image Listing V2 Refresh (30m)", 1800)
    _set_interval(PIVOT_TASK, "Materialized View Refresh (60m)", "Materialized View Refresh (30m)", 1800)
