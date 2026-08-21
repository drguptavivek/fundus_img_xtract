"""Remidio fetch adapter for the field surface.

All the machinery already exists in ``remidio_api_integration.service``; this
module adds the coalescing guard that surface lacks and narrows the result down
to state and counts.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select

from auth.utils import utcnow
from models import Job
from remidio_api_integration import service as remidio_service
from remidio_api_integration.errors import RemidioIntegrationError
from utils.log_sanitize import sanitize_log_value

from ..dto import SOURCE_REMIDIO, FetchStatusDTO
from ..exceptions import FieldConflict

logger = logging.getLogger("field_workbench.sources.remidio")

ACTIVE_JOB_STATUSES = ("queued", "processing")
RETRYABLE_JOB_STATUSES = {"failed", "partial_error", "paused"}

# A field tap is a nudge, not a backfill: the hourly beat schedule remains the
# primary pull path, so a manual fetch stays inside a narrow window.
FIELD_FETCH_WINDOW_DAYS = 1


def is_configured(db, *, project_id: int) -> bool:
    try:
        return bool(remidio_service._project_route_groups(db, project_id))
    except Exception as exc:  # noqa: BLE001 - configuration errors are not field errors
        logger.warning("Remidio configuration probe failed: %s", sanitize_log_value(exc))
        return False


def _active_job(db, project_id: int) -> Job | None:
    return db.execute(
        select(Job)
        .where(
            Job.upload_type == remidio_service.REMIDIO_API_PROJECT_SYNC_UPLOAD_TYPE,
            Job.project_id == project_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_job(db, project_id: int) -> Job | None:
    return db.execute(
        select(Job)
        .where(
            Job.upload_type == remidio_service.REMIDIO_API_PROJECT_SYNC_UPLOAD_TYPE,
            Job.project_id == project_id,
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _status_from_job(job: Job | None, *, configured: bool) -> FetchStatusDTO:
    if not configured:
        return FetchStatusDTO(
            source=SOURCE_REMIDIO,
            running=False,
            state="not_configured",
            can_retry=False,
        )
    if job is None:
        return FetchStatusDTO(source=SOURCE_REMIDIO, running=False, state="idle", can_retry=False)

    items = list(job.items or [])
    counts = {"total": len(items)}
    for item in items:
        counts[item.state] = counts.get(item.state, 0) + 1

    running = job.status in ACTIVE_JOB_STATUSES
    return FetchStatusDTO(
        source=SOURCE_REMIDIO,
        running=running,
        state="running" if running else job.status,
        last_attempt_at=job.created_at.isoformat() if job.created_at else None,
        last_success_at=job.updated_at.isoformat() if job.status == "completed" and job.updated_at else None,
        last_error=job.error,
        detail=counts,
        incomplete_count=counts.get("failed", 0) + counts.get("queued", 0) + counts.get("processing", 0),
        can_retry=job.status in RETRYABLE_JOB_STATUSES,
    )


def fetch_status(db, *, project_id: int, scope) -> FetchStatusDTO:
    configured = is_configured(db, project_id=project_id)
    job = _active_job(db, project_id) or _latest_job(db, project_id)
    return _status_from_job(job, configured=configured)


def queue_fetch(db, *, project_id: int, user, scope, remote_addr: str | None) -> FetchStatusDTO:
    if not is_configured(db, project_id=project_id):
        raise FieldConflict(
            "No Remidio API routes are configured for this project.",
            code="source_not_configured",
        )

    # Coalesce: while a fetch is in flight, report it rather than starting
    # another. This is what bounds load on the provider when several field users
    # tap at once - the per-user rate limit alone would not.
    running = _active_job(db, project_id)
    if running is not None:
        return _status_from_job(running, configured=True)

    today = utcnow().date()
    payload = {
        "start_date": (today - timedelta(days=FIELD_FETCH_WINDOW_DAYS)).isoformat(),
        "end_date": today.isoformat(),
        "mode": "field_manual",
        "limit": 100,
        "dry_run": False,
    }
    try:
        # user_id must be passed: the lab-scope check inside skips entirely when
        # it is None, which is correct for the scheduler and wrong for a person.
        result = remidio_service.create_project_sync_job(
            db,
            project_id=project_id,
            payload=payload,
            requested_by_user_id=user.id,
            requested_by_username=user.username,
            skip_active_duplicates=True,
        )
    except RemidioIntegrationError as exc:
        raise FieldConflict(str(exc), code="fetch_rejected") from exc

    job = db.get(Job, result["job_id"])
    status = _status_from_job(job, configured=True)
    if result.get("items_created"):
        # Dispatch only after the caller commits. Handing the worker a job id
        # from an uncommitted session lets it start before the rows are visible.
        status.deferred_dispatch = lambda job_id=result["job_id"], user_id=user.id: (
            remidio_service.enqueue_project_sync_job(job_id, user_id=user_id)
        )
    return status


def retry_fetch(db, *, project_id: int, user, scope, remote_addr: str | None) -> FetchStatusDTO:
    running = _active_job(db, project_id)
    if running is not None:
        return _status_from_job(running, configured=True)

    job = _latest_job(db, project_id)
    if job is None or job.status not in RETRYABLE_JOB_STATUSES:
        raise FieldConflict(
            "There is no incomplete Remidio fetch to retry.",
            code="nothing_to_retry",
        )

    try:
        remidio_service.resume_project_sync_job(db, job.id)
    except RemidioIntegrationError as exc:
        raise FieldConflict(str(exc), code="retry_rejected") from exc

    db.refresh(job)
    status = _status_from_job(job, configured=True)
    status.deferred_dispatch = lambda job_id=job.id, user_id=user.id: (
        remidio_service.enqueue_project_sync_job(job_id, user_id=user_id)
    )
    return status
