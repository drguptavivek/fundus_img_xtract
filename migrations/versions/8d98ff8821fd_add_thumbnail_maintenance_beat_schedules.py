"""add thumbnail maintenance beat schedules

Revision ID: 8d98ff8821fd
Revises: b53c2850110d
Create Date: 2026-02-13 05:16:12.937319

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d98ff8821fd'
down_revision: Union[str, Sequence[str], None] = 'b53c2850110d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Celery beat uses UTC by default in this deployment.
    op.execute("""
        INSERT INTO celery_beat_schedules
            (name, task_name, enabled, schedule_type, crontab_hour, crontab_minute, created_at, updated_at)
        VALUES
            ('Thumbnail Cleanup (07:00 IST)', 'celery_tasks.tasks.maintenance_tasks.cleanup_orphaned_thumbnails_task', true, 'crontab', '1', '30', NOW(), NOW()),
            ('Thumbnail Regeneration (13:30 IST)', 'celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_task', true, 'crontab', '8', '0', NOW(), NOW()),
            ('Thumbnail Regeneration (20:00 IST)', 'celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_task', true, 'crontab', '14', '30', NOW(), NOW()),
            ('Thumbnail Validation (19:00 IST)', 'celery_tasks.tasks.maintenance_tasks.validate_thumbnail_integrity_task', true, 'crontab', '13', '30', NOW(), NOW()),
            ('Thumbnail Full Maintenance (01:30 IST)', 'celery_tasks.tasks.maintenance_tasks.run_thumbnail_maintenance_task', true, 'crontab', '20', '0', NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            crontab_hour = EXCLUDED.crontab_hour,
            crontab_minute = EXCLUDED.crontab_minute,
            updated_at = NOW();
    """)

    op.execute("""
        INSERT INTO celery_beat_schedules
            (name, task_name, enabled, schedule_type, interval_seconds, created_at, updated_at)
        VALUES (
            'Thumbnail Regeneration (10m)',
            'celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_fast_task',
            true,
            'interval',
            600,
            NOW(),
            NOW()
        )
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            interval_seconds = EXCLUDED.interval_seconds,
            updated_at = NOW();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DELETE FROM celery_beat_schedules
        WHERE name IN (
            'Thumbnail Cleanup (07:00 IST)',
            'Thumbnail Regeneration (13:30 IST)',
            'Thumbnail Regeneration (20:00 IST)',
            'Thumbnail Validation (19:00 IST)',
            'Thumbnail Full Maintenance (01:30 IST)',
            'Thumbnail Regeneration (10m)'
        );
    """)
