from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from celery_app import celery_app

from job_store import db_set_item_state, db_set_job_status
from services.wadhwani_glaucoma_inference import run_task_inference
from remote_inference.dr_dme_service import run_encounter_inference
from utils.materialized_view_scheduler import refresh_ai_inference_runs_materialized_view
from utils.log_sanitize import sanitize_log_value


logger = logging.getLogger(__name__)
WADHWANI_BATCH_CONCURRENCY = 2
WADHWANI_FINAL_RETRY_DELAY_SECONDS = 5
WADHWANI_FINAL_RETRY_PASSES = 2
WADHWANI_FINAL_RETRY_ITEM_GAP_SECONDS = 2


def _process_wadhwani_item(job_token: str, task_id: int, user_id: int | None) -> bool:
    item_key = f"task:{task_id}"
    db_set_item_state(job_token, item_key, "processing", json.dumps({"message": "Submitting to Wadhwani"}))
    try:
        result = run_task_inference(
            task_id=task_id,
            requested_by_user_id=user_id,
            force=False,
        )
    except Exception:
        logger.error(
            "Unexpected Wadhwani item failure job=%s task_id=%s",
            sanitize_log_value(job_token),
            sanitize_log_value(task_id),
        )
        db_set_item_state(
            job_token,
            item_key,
            "error",
            json.dumps(
                {
                    "message": "Unexpected worker error while submitting to Wadhwani.",
                    "grade_id": None,
                    "inference_run_id": None,
                    "error_code": "unexpected_worker_error",
                }
            ),
        )
        return True

    state = "error" if result.status == "failed" else "ok"
    db_set_item_state(
        job_token,
        item_key,
        state,
        json.dumps(
            {
                "message": result.message,
                "grade_id": result.grade_id,
                "inference_run_id": result.inference_run_id,
                "error_code": result.error_code,
            }
        ),
    )
    return state == "error"


def _run_wadhwani_initial_pass(job_token: str, task_ids: list[int], user_id: int | None) -> list[int]:
    if not task_ids:
        return []
    with ThreadPoolExecutor(
        max_workers=min(WADHWANI_BATCH_CONCURRENCY, len(task_ids)),
        thread_name_prefix="wadhwani-batch",
    ) as executor:
        results = executor.map(
            lambda task_id: _process_wadhwani_item(job_token, task_id, user_id),
            task_ids,
        )
        return [task_id for task_id, failed in zip(task_ids, results, strict=True) if failed]


def _run_wadhwani_retry_pass(job_token: str, task_ids: list[int], user_id: int | None) -> list[int]:
    failed_task_ids: list[int] = []
    for index, task_id in enumerate(task_ids):
        if _process_wadhwani_item(job_token, task_id, user_id):
            failed_task_ids.append(task_id)
        if index < len(task_ids) - 1:
            time.sleep(WADHWANI_FINAL_RETRY_ITEM_GAP_SECONDS)
    return failed_task_ids


@celery_app.task(name="celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task", bind=True, acks_late=True)
def run_wadhwani_glaucoma_batch_task(
    self,
    job_token: str,
    task_ids: list[int],
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    db_set_job_status(job_token, "processing")

    failed_task_ids = _run_wadhwani_initial_pass(job_token, task_ids, user_id)
    for _retry_pass in range(WADHWANI_FINAL_RETRY_PASSES):
        if not failed_task_ids:
            break
        time.sleep(WADHWANI_FINAL_RETRY_DELAY_SECONDS)
        failed_task_ids = _run_wadhwani_retry_pass(job_token, failed_task_ids, user_id)
    error_count = len(failed_task_ids)

    if error_count and error_count < len(task_ids):
        db_set_job_status(job_token, "partial")
    elif error_count == len(task_ids):
        db_set_job_status(job_token, "error", error="All Wadhwani inference tasks failed.")
    else:
        db_set_job_status(job_token, "done")

    if not refresh_ai_inference_runs_materialized_view():
        logger.warning("Wadhwani batch %s completed, but ai_inference_runs_mv refresh failed", job_token)


@celery_app.task(name="celery_tasks.tasks.wadhwani_tasks.run_madhunetra_dr_dme_batch_task", bind=True, acks_late=True)
def run_madhunetra_dr_dme_batch_task(
    self,
    job_token: str,
    encounter_ids: list[int],
    user_id: int | None = None,
    hospital_id: int | None = None,
    source: str = "manual",
) -> None:
    """Process one durable MadhuNetrAI screening per EncounterSet."""
    _ = self, hospital_id
    db_set_job_status(job_token, "processing")
    errors = 0
    for encounter_id in encounter_ids:
        item_key = f"encounter:{encounter_id}"
        db_set_item_state(job_token, item_key, "processing", json.dumps({"message": "Submitting encounter to MadhuNetrAI"}))
        try:
            result = run_encounter_inference(
                encounter_id=encounter_id,
                requested_by_user_id=user_id,
                source=source,
            )
            db_set_item_state(
                job_token,
                item_key,
                "ok",
                json.dumps(
                    {
                        "message": "MadhuNetrAI screening complete.",
                        "run_id": result.run_id,
                        "request_id": result.request_id,
                        "report_id": result.report_id,
                        "status": result.status,
                        "reused": result.reused,
                    }
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.error(
                "MadhuNetrAI encounter failure job=%s encounter_id=%s error=%s",
                sanitize_log_value(job_token),
                sanitize_log_value(encounter_id),
                sanitize_log_value(exc),
            )
            db_set_item_state(
                job_token,
                item_key,
                "error",
                json.dumps(
                    {
                        "message": "MadhuNetrAI screening failed.",
                        "error_code": getattr(exc, "code", "unexpected_error"),
                    }
                ),
            )
    if errors == len(encounter_ids):
        db_set_job_status(job_token, "error", error="All MadhuNetrAI screenings failed.")
    elif errors:
        db_set_job_status(job_token, "partial")
    else:
        db_set_job_status(job_token, "done")
