from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from celery.schedules import crontab, schedule

from db_transaction_manager import transaction_scope
from models import CeleryBeatSchedule


def load_db_celery_schedules() -> Dict[str, Dict[str, Any]]:
    schedules: Dict[str, Dict[str, Any]] = {}
    with transaction_scope() as db:
        rows = (
            db.query(CeleryBeatSchedule)
            .filter(CeleryBeatSchedule.enabled.is_(True))
            .order_by(CeleryBeatSchedule.name.asc())
            .all()
        )
        for row in rows:
            task_kwargs = {"user_id": row.user_id, "hospital_id": row.hospital_id}
            if row.schedule_type == "interval":
                if not row.interval_seconds:
                    continue
                schedule_obj = schedule(timedelta(seconds=row.interval_seconds))
            else:
                schedule_obj = crontab(
                    minute=row.crontab_minute or "*",
                    hour=row.crontab_hour or "*",
                    day_of_week=row.crontab_day_of_week or "*",
                    day_of_month=row.crontab_day_of_month or "*",
                    month_of_year=row.crontab_month_of_year or "*",
                )

            entry = {
                "task": row.task_name,
                "schedule": schedule_obj,
                "kwargs": task_kwargs,
            }
            if row.queue:
                entry["options"] = {"queue": row.queue}

            schedules[row.name] = entry

    return schedules
