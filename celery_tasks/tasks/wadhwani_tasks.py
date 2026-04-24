from __future__ import annotations

import json

from celery_app import celery_app

from job_store import db_set_item_state, db_set_job_status
from services.wadhwani_glaucoma_inference import run_task_inference


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
    for task_id in task_ids:
        item_key = f"task:{task_id}"
        db_set_item_state(job_token, item_key, "processing", json.dumps({"message": "Submitting to Wadhwani"}))
        result = run_task_inference(
            task_id=task_id,
            requested_by_user_id=user_id,
            force=False,
        )
        if result.status == "failed":
            error_count += 1
            db_set_item_state(
                job_token,
                item_key,
                "error",
                json.dumps(
                    {
                        "message": result.message,
                        "grade_id": result.grade_id,
                        "inference_run_id": result.inference_run_id,
                        "error_code": result.error_code,
                    }
                ),
            )
            continue
        db_set_item_state(
            job_token,
            item_key,
            "ok",
            json.dumps(
                {
                    "message": result.message,
                    "grade_id": result.grade_id,
                    "inference_run_id": result.inference_run_id,
                    "error_code": result.error_code,
                }
            ),
        )

    if error_count and error_count < len(task_ids):
        db_set_job_status(job_token, "partial")
    elif error_count == len(task_ids):
        db_set_job_status(job_token, "error", error="All Wadhwani inference tasks failed.")
    else:
        db_set_job_status(job_token, "done")
