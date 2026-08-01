"""Recovery operations for manually submitted remote-inference jobs."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import AIInferenceRun, GradingTask, Job, JobItem
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import get_user_lab_unit_ids
from utils.celery_helpers import enqueue_task


WADHWANI_ENCOUNTER_SET_JOB_TYPE = "encounter_set_wadhwani_inference"
STALE_AFTER = timedelta(minutes=5)


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
