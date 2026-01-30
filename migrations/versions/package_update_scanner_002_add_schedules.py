"""Add package update scanner schedules

Revision ID: package_update_scanner_002
Revises: package_update_scanner_001
Create Date: 2026-01-30 12:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'package_update_scanner_002'
down_revision: Union[str, Sequence[str], None] = 'package_update_scanner_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add package update scanner Celery schedules."""
    # Insert daily package update scan schedule (runs at 3 AM UTC daily)
    # Uses NOW() for created_at/updated_at as defaults
    op.execute("""
        INSERT INTO celery_beat_schedules
            (name, task_name, enabled, schedule_type, crontab_hour, crontab_minute, created_at, updated_at)
        VALUES ('Daily Package Update Scan', 'celery_tasks.tasks.package_update_tasks.run_package_update_scan_task', true, 'crontab', '3', '0', NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            crontab_hour = EXCLUDED.crontab_hour,
            crontab_minute = EXCLUDED.crontab_minute,
            updated_at = NOW();
    """)

    # Insert daily cleanup schedule (runs at 4 AM UTC daily)
    op.execute("""
        INSERT INTO celery_beat_schedules
            (name, task_name, enabled, schedule_type, crontab_hour, crontab_minute, created_at, updated_at)
        VALUES ('Daily Package Update Cleanup', 'celery_tasks.tasks.package_update_tasks.cleanup_old_package_scans_task', true, 'crontab', '4', '0', NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            crontab_hour = EXCLUDED.crontab_hour,
            crontab_minute = EXCLUDED.crontab_minute,
            updated_at = NOW();
    """)


def downgrade() -> None:
    """Downgrade schema - remove package update scanner schedules."""
    op.execute("""
        DELETE FROM celery_beat_schedules
        WHERE name IN ('Daily Package Update Scan', 'Daily Package Update Cleanup');
    """)
