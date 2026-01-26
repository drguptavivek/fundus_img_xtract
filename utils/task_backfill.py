from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import json

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import (
    DirectImageUpload,
    DirectImageVerify,
    Disease,
    EncounterFile,
    GradingTask,
    PatientEncounters,
    TaskBackfillJob,
)
from services.taskCreationServices import ensure_task
from utils.log_sanitize import sanitize_log_value


_LOGGER = logging.getLogger("task_backfill")


def _get_disease_ids(db: Session) -> dict[str, Optional[int]]:
    glaucoma = (
        db.query(Disease.id)
        .filter(func.lower(Disease.name) == "glaucoma")
        .order_by(Disease.id)
        .first()
    )
    dr = (
        db.query(Disease.id)
        .filter(func.lower(Disease.name).in_(["diabetic retinopathy", "dr"]))
        .order_by(Disease.id)
        .first()
    )

    return {
        "glaucoma": glaucoma[0] if glaucoma else None,
        "dr": dr[0] if dr else None,
    }


def _apply_lab_unit_scope(query, allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return query.filter(False)
    return query.filter(
        or_(
            EncounterFile.lab_unit_id.in_(allowed_lab_unit_ids),
            PatientEncounters.lab_unit_id.in_(allowed_lab_unit_ids),
        )
    )


def _missing_encounter_tasks(
    db: Session,
    *,
    disease_id: int,
    allowed_lab_unit_ids: set[int],
    extra_filters: Iterable[Any],
):
    query = (
        db.query(EncounterFile)
        .join(PatientEncounters, PatientEncounters.id == EncounterFile.patient_encounter_id)
        .outerjoin(
            GradingTask,
            and_(
                GradingTask.encounter_file_id == EncounterFile.id,
                GradingTask.disease_id == disease_id,
            ),
        )
        .filter(EncounterFile.file_type == "image")
        .filter(GradingTask.id.is_(None))
    )

    query = _apply_lab_unit_scope(query, allowed_lab_unit_ids)
    for condition in extra_filters:
        query = query.filter(condition)
    return query


def _missing_direct_tasks(db: Session, *, allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return db.query(DirectImageUpload).filter(False)
    return (
        db.query(DirectImageUpload)
        .join(
            DirectImageVerify,
            DirectImageVerify.image_upload_id == DirectImageUpload.id,
        )
        .outerjoin(
            GradingTask,
            and_(
                GradingTask.direct_image_upload_id == DirectImageUpload.id,
                GradingTask.disease_id == DirectImageUpload.disease_id,
            ),
        )
        .filter(DirectImageVerify.verified_status == "verified")
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(GradingTask.id.is_(None))
    )


def get_missing_task_counts(db: Session, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    disease_ids = _get_disease_ids(db)
    counts: dict[str, int] = {
        "glaucoma": 0,
        "dr": 0,
        "no_dr": 0,
        "direct": 0,
    }

    if disease_ids["glaucoma"]:
        counts["glaucoma"] = (
            _missing_encounter_tasks(
                db,
                disease_id=disease_ids["glaucoma"],
                allowed_lab_unit_ids=allowed_lab_unit_ids,
                extra_filters=[PatientEncounters.glaucoma_verified_status == "verified"],
            ).count()
        )

    if disease_ids["dr"]:
        counts["dr"] = (
            _missing_encounter_tasks(
                db,
                disease_id=disease_ids["dr"],
                allowed_lab_unit_ids=allowed_lab_unit_ids,
                extra_filters=[PatientEncounters.dr_verified_status == "verified"],
            ).count()
        )
        counts["no_dr"] = (
            _missing_encounter_tasks(
                db,
                disease_id=disease_ids["dr"],
                allowed_lab_unit_ids=allowed_lab_unit_ids,
                extra_filters=[
                    PatientEncounters.encounter_verified_status == "verified",
                    or_(
                        PatientEncounters.dr_verified_status.is_(None),
                        PatientEncounters.dr_verified_status != "verified",
                    ),
                ],
            ).count()
        )

    counts["direct"] = _missing_direct_tasks(
        db,
        allowed_lab_unit_ids=allowed_lab_unit_ids,
    ).count()

    return counts


def run_task_backfill(
    db: Session,
    *,
    allowed_lab_unit_ids: set[int],
    limit: Optional[int] = None,
    progress_cb: Optional[Callable[[bool], None]] = None,
) -> dict[str, int]:
    disease_ids = _get_disease_ids(db)
    remaining = limit if limit is not None else None
    results = {
        "created": 0,
        "errors": 0,
    }

    def _iter_rows(query):
        if remaining is None:
            return query.all()
        return query.limit(remaining).all()

    def _consume_query(query, disease_id: Optional[int] = None):
        nonlocal remaining
        for row in _iter_rows(query):
            if remaining is not None and remaining <= 0:
                break
            try:
                if isinstance(row, EncounterFile):
                    ensure_task(row.uuid, disease_id, db)
                else:
                    ensure_task(row.uuid, row.disease_id, db)
                results["created"] += 1
                if progress_cb:
                    progress_cb(True)
                if remaining is not None:
                    remaining -= 1
            except Exception as exc:  # noqa: BLE001
                results["errors"] += 1
                if progress_cb:
                    progress_cb(False)
                _LOGGER.exception(
                    "Task backfill failed for image %s: %s",
                    sanitize_log_value(getattr(row, "uuid", "unknown")),
                    sanitize_log_value(exc),
                )

    if disease_ids["glaucoma"]:
        query = _missing_encounter_tasks(
            db,
            disease_id=disease_ids["glaucoma"],
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            extra_filters=[PatientEncounters.glaucoma_verified_status == "verified"],
        )
        _consume_query(query, disease_ids["glaucoma"])

    if disease_ids["dr"]:
        query = _missing_encounter_tasks(
            db,
            disease_id=disease_ids["dr"],
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            extra_filters=[PatientEncounters.dr_verified_status == "verified"],
        )
        _consume_query(query, disease_ids["dr"])

        query = _missing_encounter_tasks(
            db,
            disease_id=disease_ids["dr"],
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            extra_filters=[
                PatientEncounters.encounter_verified_status == "verified",
                or_(
                    PatientEncounters.dr_verified_status.is_(None),
                    PatientEncounters.dr_verified_status != "verified",
                ),
            ],
        )
        _consume_query(query, disease_ids["dr"])

    query = _missing_direct_tasks(
        db,
        allowed_lab_unit_ids=allowed_lab_unit_ids,
    )
    _consume_query(query)

    return results


def run_task_backfill_job(job_id: int) -> None:
    with get_db_session() as db:
        job = db.get(TaskBackfillJob, job_id)
        if not job:
            return
        if job.status not in {"queued", "running"}:
            return

        allowed_lab_unit_ids: set[int] = set()
        if job.allowed_lab_unit_ids:
            try:
                allowed_lab_unit_ids = set(json.loads(job.allowed_lab_unit_ids))
            except (TypeError, json.JSONDecodeError):
                allowed_lab_unit_ids = set()
        totals = get_missing_task_counts(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
        job.status = "running"
        job.started_at = utcnow()
        job.total_candidates = sum(totals.values())
        job.processed_count = 0
        job.created_count = 0
        job.error_count = 0
        job.error_message = None
        db.add(job)
        db.commit()

        processed_since_commit = 0

        def _progress(success: bool) -> None:
            nonlocal processed_since_commit
            job.processed_count += 1
            if success:
                job.created_count += 1
            else:
                job.error_count += 1
            processed_since_commit += 1
            if processed_since_commit >= 25:
                db.add(job)
                db.commit()
                processed_since_commit = 0

        try:
            run_task_backfill(
                db,
                allowed_lab_unit_ids=allowed_lab_unit_ids,
                limit=job.requested_limit,
                progress_cb=_progress,
            )
            job.status = "completed"
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error_message = str(exc)
            _LOGGER.exception(
                "Task backfill job %s failed: %s",
                sanitize_log_value(job_id),
                sanitize_log_value(exc),
            )
        finally:
            job.finished_at = utcnow()
            db.add(job)
            db.commit()


def enqueue_task_backfill(
    app,
    job_id: int,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    from utils.celery_helpers import enqueue_task, celery_enabled
    if celery_enabled():
        enqueue_task(
            "celery_tasks.tasks.task_backfill_tasks.run_task_backfill_job_task",
            job_id,
            user_id=user_id,
            hospital_id=hospital_id,
        )
        return
    executor = app.config.get("EXECUTOR")
    if executor is None:
        return

    def _worker(app_ref, job_id_val: int) -> None:
        with app_ref.app_context():
            run_task_backfill_job(job_id_val)

    executor.submit(_worker, app, job_id)
