from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import redis
import sqlalchemy as sa

from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import AppSetting, Job, JobItem, Role, User
from utils.emails import send_email_sync
from utils.log_sanitize import sanitize_log_value
from utils.redis_connection import build_redis_url

_LOGGER = logging.getLogger("maintenance")

MONITORED_QUEUES = (
    "zip_ocr",
    "pii_detection",
    "metadata",
    "thumbnails",
    "maintenance",
    "exports",
    "s3_sync",
    "default",
)

DEFAULT_QUEUE_THRESHOLDS = {
    "zip_ocr": (25, 100),
    "pii_detection": (25, 100),
    "metadata": (50, 200),
    "thumbnails": (50, 200),
    "maintenance": (25, 100),
    "exports": (10, 25),
    "s3_sync": (50, 200),
    "default": (25, 100),
}

LAST_ALERT_SETTING_KEY = "celery_queue_alert_last_sent_at"


@dataclass(frozen=True)
class QueueThreshold:
    warning: int
    critical: int


def _env_bool(key: str, default: str = "true") -> bool:
    return str(os.getenv(key, default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return max(minimum, int(raw.strip()))
    except ValueError:
        return default


def _threshold_for(queue_name: str) -> QueueThreshold:
    warning_default, critical_default = DEFAULT_QUEUE_THRESHOLDS.get(queue_name, (25, 100))
    prefix = f"CELERY_QUEUE_{queue_name.upper()}_"
    warning = _env_int(f"{prefix}WARNING", warning_default, minimum=1)
    critical = _env_int(f"{prefix}CRITICAL", critical_default, minimum=warning)
    return QueueThreshold(warning=warning, critical=critical)


def _queue_state(depth: int, threshold: QueueThreshold) -> str:
    if depth >= threshold.critical:
        return "critical"
    if depth >= threshold.warning:
        return "warning"
    return "healthy"


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(build_redis_url(), socket_connect_timeout=2, socket_timeout=2)


def _get_queue_depths() -> tuple[list[dict[str, Any]], str | None]:
    try:
        client = _redis_client()
        rows = []
        for queue_name in MONITORED_QUEUES:
            threshold = _threshold_for(queue_name)
            depth = int(client.llen(queue_name))
            rows.append(
                {
                    "name": queue_name,
                    "depth": depth,
                    "warning_threshold": threshold.warning,
                    "critical_threshold": threshold.critical,
                    "status": _queue_state(depth, threshold),
                }
            )
        return rows, None
    except Exception as exc:
        _LOGGER.warning("Celery queue depth check failed: %s", sanitize_log_value(exc))
        return [], str(exc)


def _get_oldest_active_zip_job(stale_minutes: int) -> dict[str, Any] | None:
    cutoff = utcnow() - timedelta(minutes=stale_minutes)
    with transaction_scope() as db:
        row = (
            db.query(Job, sa.func.min(sa.func.coalesce(JobItem.started_at, JobItem.finished_at, Job.created_at)))
            .join(JobItem, JobItem.job_id == Job.id)
            .filter(Job.upload_type == "zip upload")
            .filter(Job.status.in_(["queued", "processing"]))
            .filter(JobItem.state.in_(["queued", "processing"]))
            .group_by(Job.id)
            .order_by(sa.func.min(sa.func.coalesce(JobItem.started_at, JobItem.finished_at, Job.created_at)).asc())
            .first()
        )
        if not row:
            return None
        job, oldest_marker = row
        if not oldest_marker:
            oldest_marker = job.created_at
        if oldest_marker.tzinfo is None:
            oldest_marker = oldest_marker.replace(tzinfo=timezone.utc)
        age_minutes = int((utcnow() - oldest_marker).total_seconds() // 60)
        if oldest_marker >= cutoff:
            return None
        return {
            "job_id": job.id,
            "token": job.token,
            "status": job.status,
            "upload_type": job.upload_type,
            "uploader_username": job.uploader_username,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "oldest_active_at": oldest_marker.isoformat(),
            "age_minutes": age_minutes,
            "stale_minutes": stale_minutes,
        }


def get_celery_queue_health() -> dict[str, Any]:
    """Return Redis queue depth and stale ZIP job health for dashboards and alerts."""
    queue_rows, redis_error = _get_queue_depths()
    stale_minutes = _env_int("CELERY_QUEUE_STALE_ZIP_JOB_MINUTES", 30, minimum=1)
    stale_zip_job = None
    stale_error = None
    try:
        stale_zip_job = _get_oldest_active_zip_job(stale_minutes)
    except Exception as exc:
        stale_error = str(exc)
        _LOGGER.warning("Celery stale ZIP job check failed: %s", sanitize_log_value(exc))

    queue_problem_count = sum(1 for row in queue_rows if row["status"] != "healthy")
    critical_count = sum(1 for row in queue_rows if row["status"] == "critical")
    status = "healthy"
    issues: list[str] = []
    if redis_error or stale_error:
        status = "critical"
        if redis_error:
            issues.append(f"Redis queue depth check failed: {redis_error}")
        if stale_error:
            issues.append(f"Stale ZIP job check failed: {stale_error}")
    if critical_count:
        status = "critical"
        issues.append(f"{critical_count} Celery queue(s) are above critical depth")
    elif queue_problem_count and status == "healthy":
        status = "warning"
        issues.append(f"{queue_problem_count} Celery queue(s) are above warning depth")
    if stale_zip_job:
        status = "critical"
        issues.append(
            f"ZIP upload job {stale_zip_job['job_id']} has active items older than "
            f"{stale_zip_job['stale_minutes']} minutes"
        )

    return {
        "timestamp": utcnow().isoformat(),
        "status": status,
        "issues": issues,
        "queues": queue_rows,
        "stale_zip_job": stale_zip_job,
        "summary": {
            "queue_problem_count": queue_problem_count,
            "critical_count": critical_count,
            "monitored_queue_count": len(MONITORED_QUEUES),
            "stale_zip_job": bool(stale_zip_job),
        },
    }


def _last_alert_sent_at(db) -> datetime | None:
    setting = db.get(AppSetting, LAST_ALERT_SETTING_KEY)
    if not setting or not setting.value:
        return None
    try:
        value = datetime.fromisoformat(setting.value)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _store_last_alert_sent_at(db, sent_at: datetime) -> None:
    value = sent_at.isoformat()
    setting = db.get(AppSetting, LAST_ALERT_SETTING_KEY)
    if setting:
        setting.value = value
        setting.value_type = "datetime"
        setting.updated_at = sent_at
    else:
        db.add(AppSetting(key=LAST_ALERT_SETTING_KEY, value=value, value_type="datetime"))


def _active_admin_emails() -> list[str]:
    with transaction_scope() as db:
        rows = (
            db.query(User.email)
            .join(User.roles)
            .filter(Role.name == "admin")
            .filter(User.is_active.is_(True))
            .filter(User.email.isnot(None))
            .order_by(User.username.asc())
            .all()
        )
    return sorted({email.strip() for (email,) in rows if email and email.strip()})


def _should_send_alert(now: datetime, cooldown_minutes: int) -> bool:
    with transaction_scope() as db:
        last_sent_at = _last_alert_sent_at(db)
        if last_sent_at and now - last_sent_at < timedelta(minutes=cooldown_minutes):
            return False
        _store_last_alert_sent_at(db, now)
        return True


def _format_alert_body(health: dict[str, Any]) -> str:
    lines = [
        "Celery queue health is not healthy.",
        "",
        f"Status: {health['status']}",
        f"Checked at: {health['timestamp']}",
        "",
        "Issues:",
    ]
    lines.extend(f"- {issue}" for issue in health.get("issues") or ["No issue details available"])
    lines.extend(["", "Queue depths:"])
    for row in health.get("queues", []):
        lines.append(
            f"- {row['name']}: {row['depth']} "
            f"(warn {row['warning_threshold']}, critical {row['critical_threshold']}, {row['status']})"
        )
    stale_job = health.get("stale_zip_job")
    if stale_job:
        lines.extend(
            [
                "",
                "Oldest stale ZIP job:",
                f"- Job ID: {stale_job['job_id']}",
                f"- Token: {stale_job['token']}",
                f"- Status: {stale_job['status']}",
                f"- Uploader: {stale_job.get('uploader_username') or 'unknown'}",
                f"- Created at: {stale_job.get('created_at') or 'unknown'}",
                f"- Oldest active item at: {stale_job['oldest_active_at']}",
                f"- Age: {stale_job['age_minutes']} minutes",
            ]
        )
    lines.extend(["", "Open Admin Status > Celery Schedules / Queue Health for live details."])
    return "\n".join(lines)


def check_celery_queues_and_alert() -> dict[str, Any]:
    """Check queue health and send a throttled email alert to active admins."""
    health = get_celery_queue_health()
    if not _env_bool("CELERY_QUEUE_ALERT_ENABLED", "true"):
        health["alert"] = {"enabled": False, "sent": False, "reason": "disabled"}
        return health
    if health["status"] == "healthy":
        health["alert"] = {"enabled": True, "sent": False, "reason": "healthy"}
        return health

    cooldown_minutes = _env_int("CELERY_QUEUE_ALERT_COOLDOWN_MINUTES", 60, minimum=1)
    now = utcnow()
    if not _should_send_alert(now, cooldown_minutes):
        health["alert"] = {"enabled": True, "sent": False, "reason": "cooldown"}
        return health

    recipients = _active_admin_emails()
    if not recipients:
        health["alert"] = {"enabled": True, "sent": False, "reason": "no_admin_emails"}
        _LOGGER.warning("Celery queue alert suppressed because no active admin email exists")
        return health

    subject = f"[Fundus Image Manager] Celery queue {health['status']} alert"
    body = _format_alert_body(health)
    sent_count = 0
    first, *cc = recipients
    if send_email_sync(first, subject, body, cc_emails=cc, sensitive=True):
        sent_count = len(recipients)
    health["alert"] = {
        "enabled": True,
        "sent": sent_count > 0,
        "recipient_count": len(recipients),
        "sent_count": sent_count,
    }
    return health
