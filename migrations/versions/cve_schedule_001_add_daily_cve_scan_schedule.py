"""Add daily CVE scan schedule

Revision ID: cve_schedule_001
Revises: 9432de97be99
Create Date: 2026-01-30 03:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cve_schedule_001'
down_revision = '9432de97be99'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Insert daily CVE scan schedule (runs at 2 AM UTC daily)
    # Uses NOW() for created_at/updated_at as defaults
    op.execute("""
        INSERT INTO celery_beat_schedules
            (name, task_name, enabled, schedule_type, crontab_hour, crontab_minute, created_at, updated_at)
        VALUES ('Daily CVE Scan', 'celery_tasks.tasks.cve_tasks.run_cve_scan_task', true, 'crontab', '2', '0', NOW(), NOW())
        ON CONFLICT (name) DO UPDATE SET
            task_name = EXCLUDED.task_name,
            enabled = EXCLUDED.enabled,
            schedule_type = EXCLUDED.schedule_type,
            crontab_hour = EXCLUDED.crontab_hour,
            crontab_minute = EXCLUDED.crontab_minute,
            updated_at = NOW()
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM celery_beat_schedules WHERE name = 'Daily CVE Scan'
    """)
