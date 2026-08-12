from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from celery_app import celery_app

from job_store import db_set_item_state, db_set_job_status
from services.wadhwani_glaucoma_inference import run_task_inference
from utils.materialized_view_scheduler import refresh_ai_inference_runs_materialized_view
from utils.log_sanitize import sanitize_log_value


logger = logging.getLogger(__name__)
WADHWANI_BATCH_CONCURRENCY = 3


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


@celery_app.task(name="celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task", bind=True, acks_late=True)
def run_wadhwani_glaucoma_batch_task(
    self,
    job_token: str,
    task_ids: list[int],
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    db_set_job_status(job_token, "processing")

    error_count = 0
    if task_ids:
        with ThreadPoolExecutor(
            max_workers=min(WADHWANI_BATCH_CONCURRENCY, len(task_ids)),
            thread_name_prefix="wadhwani-batch",
        ) as executor:
            error_count = sum(
                executor.map(
                    lambda task_id: _process_wadhwani_item(job_token, task_id, user_id),
                    task_ids,
                )
            )

    if error_count and error_count < len(task_ids):
        db_set_job_status(job_token, "partial")
    elif error_count == len(task_ids):
        db_set_job_status(job_token, "error", error="All Wadhwani inference tasks failed.")
    else:
        db_set_job_status(job_token, "done")

    if not refresh_ai_inference_runs_materialized_view():
        logger.warning("Wadhwani batch %s completed, but ai_inference_runs_mv refresh failed", job_token)
