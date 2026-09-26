"""Queued project workbook exports for desktop mirrors.

The workbook is the same one the project workspace produces
(``project_review.export_service``); it runs on the Celery ``exports`` queue so
a sync client never builds it inside a web worker. One active export per grant.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from auth.utils import utcnow
from job_store import db_create_job
from models import Job
from project_review.export_service import EXPORT_DIR, enqueue_project_export, validate_export_request

from .dto import SyncContext
from .exceptions import ProjectSyncConflict, ProjectSyncNotFound

UPLOAD_TYPE = "project_sync_export"
ACTIVE_STATUSES = ("queued", "processing")
STALE_AFTER = timedelta(hours=6)


@dataclass(frozen=True)
class SyncExportJob:
    token: str
    status: str
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None
    files: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "job_token": self.token,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "files": list(self.files),
        }


def _export_dir(token: str) -> Path | None:
    path = (EXPORT_DIR / token).resolve()
    return path if EXPORT_DIR.resolve() in path.parents else None


def _files(job: Job) -> tuple[str, ...]:
    path = _export_dir(job.token)
    if job.status != "done" or path is None or not path.is_dir():
        return ()
    return tuple(sorted(item.name for item in path.iterdir() if item.is_file()))


def _to_dto(job: Job) -> SyncExportJob:
    return SyncExportJob(job.token, job.status, getattr(job, "error", None), job.created_at, job.updated_at, _files(job))


def _jobs(db, ctx: SyncContext):
    return select(Job).where(
        Job.project_id == ctx.project_id,
        Job.uploader_user_id == ctx.user_id,
        Job.upload_type == UPLOAD_TYPE,
    )


def request_export(db, ctx: SyncContext, *, app, ip_address: str | None) -> SyncExportJob:
    # A job stuck in the queue for hours (worker outage) must not block forever.
    stale_before = utcnow() - STALE_AFTER
    active = db.execute(
        _jobs(db, ctx).where(Job.status.in_(ACTIVE_STATUSES), Job.created_at > stale_before).limit(1)
    ).scalar_one_or_none()
    if active is not None:
        raise ProjectSyncConflict("An export for this grant is already queued.", code="export_in_progress")
    request = validate_export_request(
        project_id=ctx.project_id, actor_user_id=ctx.user_id, kind="workbook",
        date_from=None, date_to=None, grading_filter="all",
    )
    token = db_create_job(
        ["project_export"], [],
        uploader_user_id=ctx.user_id,
        uploader_username=ctx.username,
        uploader_ip=ip_address or "-",
        project_id=ctx.project_id,
        upload_type=UPLOAD_TYPE,
    )
    enqueue_project_export(
        app,
        token,
        {
            "project_id": request.project_id,
            "actor_user_id": request.actor_user_id,
            "kind": request.kind,
            "date_from": None,
            "date_to": None,
            "grading_filter": request.grading_filter,
            "sync_grant_uuid": ctx.grant_uuid,
        },
    )
    job = db.execute(select(Job).where(Job.token == token)).scalar_one_or_none()
    return _to_dto(job) if job is not None else SyncExportJob(token, "queued", None, None, None, ())


def latest_export(db, ctx: SyncContext) -> SyncExportJob | None:
    job = db.execute(_jobs(db, ctx).order_by(Job.created_at.desc(), Job.id.desc()).limit(1)).scalar_one_or_none()
    return _to_dto(job) if job is not None else None


def export_file(db, ctx: SyncContext, *, token: str, filename: str) -> Path:
    job = db.execute(_jobs(db, ctx).where(Job.token == token)).scalar_one_or_none()
    if job is None or filename not in _files(job):
        raise ProjectSyncNotFound("Export file not found.")
    return _export_dir(token) / filename
