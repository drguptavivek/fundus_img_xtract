"""Recovery operations for manually submitted remote-inference jobs."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import AIInferenceRun, GradingTask, Job, JobItem
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import get_user_lab_unit_ids
from utils.celery_helpers import enqueue_task


WADHWANI_ENCOUNTER_SET_JOB_TYPE = "encounter_set_wadhwani_inference"
WADHWANI_RETRY_JOB_TYPE = "wai_api_statistics_retry"
STALE_AFTER = timedelta(minutes=5)


@dataclass(frozen=True)
class RecentWadhwaniJob:
    token: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None
    total_count: int
    queued_count: int
    processing_count: int
    completed_count: int
    failed_count: int


def list_recent_encounter_set_wadhwani_jobs(
    db,
    *,
    project_id: int,
    allowed_lab_unit_ids: set[int],
    limit: int = 10,
) -> list[RecentWadhwaniJob]:
    """Return recent project jobs restricted to the caller's lab-unit scope."""
    if not allowed_lab_unit_ids:
        return []
    candidate_jobs = (
        db.execute(
            select(Job)
            .options(selectinload(Job.items))
            .where(
                Job.project_id == project_id,
                Job.upload_type.in_((WADHWANI_ENCOUNTER_SET_JOB_TYPE, WADHWANI_RETRY_JOB_TYPE)),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    task_ids = {
        task_id
        for job in candidate_jobs
        for item in job.items
        if (task_id := task_id_from_job_item(item)) is not None
    }
    task_lab_by_id = {
        task_id: lab_unit_id
        for task_id, lab_unit_id in db.execute(
            select(GradingTask.id, GradingTask.lab_unit_id).where(GradingTask.id.in_(task_ids))
        ).all()
    } if task_ids else {}
    rows = []
    result_limit = max(1, min(limit, 10))
    for job in candidate_jobs:
        job_task_lab_ids = {
            task_lab_by_id[task_id]
            for item in job.items
            if (task_id := task_id_from_job_item(item)) in task_lab_by_id
        }
        if job_task_lab_ids:
            if not job_task_lab_ids.issubset(allowed_lab_unit_ids):
                continue
        elif job.lab_unit_id not in allowed_lab_unit_ids:
            continue
        counts = {"queued": 0, "processing": 0, "ok": 0, "error": 0}
        for item in job.items:
            state = str(item.state or "queued").lower()
            counts[state if state in counts else "queued"] += 1
        rows.append(
            RecentWadhwaniJob(
                token=job.token,
                status=job.status,
                created_at=job.created_at,
                updated_at=job.updated_at,
                total_count=len(job.items),
                queued_count=counts["queued"],
                processing_count=counts["processing"],
                completed_count=counts["ok"],
                failed_count=counts["error"],
            )
        )
        if len(rows) >= result_limit:
            break
    return rows


def task_id_from_job_item(item: JobItem) -> int | None:
    if item.task_id:
        return item.task_id
    value = str(item.filename or "")
    if not value.startswith("task:"):
        return None
    try:
        return int(value.split(":", 1)[1])
    except (TypeError, ValueError):
        return None


def is_job_resumable(job: Job, items: list[JobItem], *, now=None) -> bool:
    """Return true only after an unfinished batch has stopped updating long enough."""
    if job.upload_type != WADHWANI_ENCOUNTER_SET_JOB_TYPE or job.status != "processing":
        return False
    unfinished = [item for item in items if item.state in {"queued", "processing"}]
    if not unfinished:
        return False
    cutoff = (now or utcnow()) - STALE_AFTER
    processing = [item for item in unfinished if item.state == "processing"]
    if processing:
        return all(item.started_at is not None and item.started_at <= cutoff for item in processing)
    return job.updated_at is not None and job.updated_at <= cutoff


def resume_interrupted_wadhwani_job(*, job_token: str, user_id: int) -> MutationResult:
    """Checkpoint an interrupted batch and requeue only its unfinished task IDs."""
    allowed_lab_ids = get_user_lab_unit_ids(user_id)
    if not allowed_lab_ids:
        return MutationResult(False, "You are not assigned to any lab units for this batch.", 403)

    with transaction_scope() as db:
        job = db.execute(
            select(Job).where(Job.token == job_token).with_for_update()
        ).scalar_one_or_none()
        if job is None or job.upload_type != WADHWANI_ENCOUNTER_SET_JOB_TYPE:
            return MutationResult(False, "Wadhwani inference batch not found.", 404)
        items = db.execute(
            select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)
        ).scalars().all()
        if not is_job_resumable(job, items):
            return MutationResult(False, "This batch is not interrupted or is not yet stale enough to resume.", 409)

        unfinished = [item for item in items if item.state in {"queued", "processing"}]
        task_ids = [task_id for item in unfinished if (task_id := task_id_from_job_item(item)) is not None]
        if not task_ids:
            return MutationResult(False, "No unfinished inference tasks were found.", 409)

        task_lab_ids = {
            row[0]
            for row in db.execute(
                select(GradingTask.lab_unit_id).where(GradingTask.id.in_(task_ids))
            ).all()
            if row[0] is not None
        }
        if not task_lab_ids or not task_lab_ids.issubset(allowed_lab_ids):
            return MutationResult(False, "You do not have access to every unfinished task in this batch.", 403)

        abandoned_runs = db.execute(
            select(AIInferenceRun).where(
                AIInferenceRun.task_id.in_(task_ids),
                AIInferenceRun.status == "running",
            )
        ).scalars().all()
        finished_at = utcnow()
        for run in abandoned_runs:
            run.status = "failed"
            run.error_code = "worker_interrupted"
            run.error_message = "Inference worker stopped before the remote request completed."
            run.finished_at = finished_at

        detail = json.dumps({"message": "Requeued after interrupted inference worker."})
        for item in unfinished:
            item.state = "queued"
            item.detail = detail
            item.started_at = None
            item.finished_at = None
        job.status = "queued"
        job.error = None
        requested_by_user_id = job.uploader_user_id or user_id
        db.flush()

    try:
        enqueue_task(
            "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task",
            job_token,
            task_ids,
            user_id=requested_by_user_id,
        )
    except Exception:
        with transaction_scope() as db:
            job = db.execute(select(Job).where(Job.token == job_token).with_for_update()).scalar_one_or_none()
            if job is not None:
                job.status = "error"
                job.error = "Could not requeue the interrupted Wadhwani inference batch."
        return MutationResult(False, "Could not requeue the interrupted Wadhwani inference batch.", 503)

    return MutationResult(
        True,
        f"Resumed {len(task_ids)} unfinished Wadhwani inference task(s).",
        payload={"job_token": job_token, "resumed_task_count": len(task_ids)},
    )
