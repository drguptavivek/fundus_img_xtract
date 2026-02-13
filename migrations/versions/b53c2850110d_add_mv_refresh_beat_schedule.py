"""add mv refresh beat schedule

Revision ID: b53c2850110d
Revises: ab12cd34ef56
Create Date: 2026-02-13 05:10:44.719698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b53c2850110d'
down_revision: Union[str, Sequence[str], None] = 'ab12cd34ef56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        INSERT INTO celery_beat_schedules
            (name, task_name, enabled, schedule_type, interval_seconds, created_at, updated_at)
        VALUES (
            'Materialized View Refresh (30m)',
            'celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task',
            true,
            'interval',
            1800,
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
        WHERE name = 'Materialized View Refresh (30m)';
    """)
