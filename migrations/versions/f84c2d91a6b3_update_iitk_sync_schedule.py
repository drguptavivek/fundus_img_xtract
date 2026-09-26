"""Update IITK sync schedule to hourly at :05 IST.

Revision ID: f84c2d91a6b3
Revises: cecc7e9b8613
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f84c2d91a6b3"
down_revision = "cecc7e9b8613"
branch_labels = None
depends_on = None

SCHEDULE_NAME = "IITK API EncounterSet Sync Hourly IST Business Hours"


def _set_schedule(*, hour: str, minute: str) -> None:
    if "celery_beat_schedules" not in inspect(op.get_bind()).get_table_names():
        return
    op.execute(
        sa.text(
            """
            UPDATE celery_beat_schedules
            SET crontab_hour = :hour,
                crontab_minute = :minute,
                updated_at = NOW()
            WHERE name = :name
            """
        ).bindparams(name=SCHEDULE_NAME, hour=hour, minute=minute)
    )


def upgrade():
    # Celery Beat uses UTC: 02:35-11:35 UTC is 08:05-17:05 IST.
    _set_schedule(hour="2-11", minute="35")


def downgrade():
    # Restore the prior 07:00-18:00 IST schedule.
    _set_schedule(hour="1-12", minute="30")
