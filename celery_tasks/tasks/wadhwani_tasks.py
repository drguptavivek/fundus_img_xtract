from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from celery_app import celery_app

from job_store import db_set_item_state, db_set_job_status
from services.wadhwani_glaucoma_inference import run_task_inference
from remote_inference.dr_dme_service import run_encounter_inference
from utils.error_sanitization import sanitize_exception_message
from utils.materialized_view_scheduler import refresh_ai_inference_runs_materialized_view
from utils.log_sanitize import sanitize_log_value


logger = logging.getLogger(__name__)
wai_logger = logging.getLogger("wai")
WADHWANI_BATCH_CONCURRENCY = 2
WADHWANI_FINAL_RETRY_DELAY_SECONDS = 5
WADHWANI_FINAL_RETRY_PASSES = 2
WADHWANI_FINAL_RETRY_ITEM_GAP_SECONDS = 2


@celery_app.task(name="celery_tasks.tasks.wadhwani_tasks.run_project_wai_backfill_task", bind=True, acks_late=True)
def run_project_wai_backfill_task(
    self,
    job_token: str,
    project_id: int,
    user_id: int | None = None,
    username: str | None = None,
    remote_addr: str | None = None,
    hospital_id: int | None = None,
) -> None:
    """Dispatch every configured, still-eligible WAI workflow for a project."""
    from remote_inference.project_backfill_service import ITEM_KEY

    # The common task dispatcher includes hospital_id for all tasks. This job
    # is project-wide; the value must not narrow its authorized project scope.
    _ = hospital_id
    try:
        from remote_inference.encounter_service import enqueue_automatic_encounters
        from remote_inference.project_backfill_service import project_encounter_ids
        from services.encounter_set_ai_inference import enqueue_wadhwani_for_encounter_ids

        db_set_job_status(job_token, "processing")
        db_set_item_state(job_token, ITEM_KEY, "processing", json.dumps({"message": "Scanning project EncounterSets."}))
        encounter_ids = project_encounter_ids(project_id)
        dr_result = {"madhunetra_encounters_queued": 0, "madhunetra_job_tokens": []}
        glaucoma_result = {"wadhwani_tasks_queued": 0, "wadhwani_job_tokens": []}
        for offset in range(0, len(encounter_ids), 500):
            chunk = encounter_ids[offset:offset + 500]
            chunk_dr = enqueue_automatic_encounters(chunk, user_id=user_id)
            dr_result["madhunetra_encounters_queued"] += chunk_dr["madhunetra_encounters_queued"]
            dr_result["madhunetra_job_tokens"].extend(chunk_dr["madhunetra_job_tokens"])
            chunk_glaucoma = enqueue_wadhwani_for_encounter_ids(
                chunk,
                user_id=user_id,
                username=username,
                remote_addr=remote_addr,
                include_all_trigger_timings=True,
            )
            glaucoma_result["wadhwani_tasks_queued"] += chunk_glaucoma["wadhwani_tasks_queued"]
            glaucoma_result["wadhwani_job_tokens"].extend(chunk_glaucoma["wadhwani_job_tokens"])
        detail = {
            "message": "Configured WAI workflows dispatched.",
            "encounters_scanned": len(encounter_ids),
            **dr_result,
            **glaucoma_result,
        }
        db_set_item_state(job_token, ITEM_KEY, "ok", json.dumps(detail))
        db_set_job_status(job_token, "done")
    except Exception:
        logger.exception("Project WAI dispatcher failed job=%s", sanitize_log_value(job_token))
        db_set_item_state(
            job_token,
            ITEM_KEY,
            "error",
            json.dumps({"message": "Project WAI dispatcher failed."}),
        )
        db_set_job_status(job_token, "error", error="Project WAI dispatcher failed.")


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
            safe_error = sanitize_log_value(
                sanitize_exception_message(str(exc)), max_len=500
            )
            logger.error(
                "MadhuNetrAI encounter failure job=%s encounter_id=%s error=%s",
                sanitize_log_value(job_token),
                sanitize_log_value(encounter_id),
                safe_error,
            )
            wai_logger.error(
                "provider_failure provider=madhunetrai workflow=dr_dme "
                "job=%s encounter_id=%s stage=%s error_code=%s "
                "http_status=%s retryable=%s message=%s",
                sanitize_log_value(job_token),
                sanitize_log_value(encounter_id),
                sanitize_log_value(getattr(exc, "step", "unknown")),
                sanitize_log_value(getattr(exc, "code", "unexpected_error")),
                sanitize_log_value(getattr(exc, "status_code", None)),
                sanitize_log_value(getattr(exc, "retryable", False)),
                safe_error,
            )
            db_set_item_state(
                job_token,
                item_key,
                "error",
                json.dumps(
                    {
                        "message": "MadhuNetrAI screening failed.",
                        "error_code": getattr(exc, "code", "unexpected_error"),
                        # Without the detail, an ineligible_encounter or http_error
                        # says nothing about which rule failed or which URL 404'd,
                        # and the job page cannot explain itself.
                        "detail": str(safe_error)[:500],
                    }
                ),
            )
    if errors == len(encounter_ids):
        db_set_job_status(job_token, "error", error="All MadhuNetrAI screenings failed.")
    elif errors:
        db_set_job_status(job_token, "partial")
    else:
        db_set_job_status(job_token, "done")
