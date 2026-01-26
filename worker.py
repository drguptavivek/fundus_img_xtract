# worker.py
from pathlib import Path
from flask import current_app
from models import Session
from zip_processor import setup_environment,  process_zip_file
from process_pdfs import process_all_pdfs_for_ocr
from job_store import (
    db_set_job_status, db_set_item_state, db_any_item_error,
)

def _process_one_zip(zip_path: Path) -> dict:
    """
    Reuse existing pipeline:
      - setup env & db
      - process_zip_file(zip_path, db)     # extract + DB + moves zip
      - process_all_pdfs_for_ocr()         # OCR all PDFs (your current runner behavior)
    """
    setup_environment()
    db = Session()
    try:
        pdfs, status = process_zip_file(zip_path, db)
        
        # Handle different status values from process_zip_file
        if status == "duplicate":
            return {"status": "skipped", "message": f"Duplicate file (already processed)"}
        elif status == "error":
            return {"status": "error", "message": "Processing error"}
        elif status == "skipped":
            return {"status": "skipped", "message": "File skipped (resource fork or invalid)"}
        
        # For normal processing ("ok" status)
        if not pdfs:
            # Nothing extracted (e.g., images only), treat as ok but skip OCR
            return {"status": "ok", "message": "Ingested (no PDFs to OCR)"}
        # Limit OCR strictly to PDFs from this zip
        process_all_pdfs_for_ocr(limit_filenames=set(pdfs))
        return {"status": "ok", "message": f"Ingested + OCR for {len(pdfs)} PDF(s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

def process_zip_job(job_token: str, saved_paths: list[Path]):
    db_set_job_status(job_token, "processing")
    try:
        for p in saved_paths:
            db_set_item_state(job_token, p.name, "processing")
            result = _process_one_zip(p)
            # Map statuses to appropriate job item states
            if result["status"] == "skipped" and "Duplicate file" in result.get("message", ""):
                # Mark duplicate files as rejected (error state)
                item_status = "error"
            elif result["status"] == "skipped":
                # Other skipped files (resource fork, etc.) remain as ok
                item_status = "ok"
            else:
                # Use the status as-is for ok/error
                item_status = result["status"]
            db_set_item_state(job_token, p.name, item_status, result.get("message"))
        if db_any_item_error(job_token):
            db_set_job_status(job_token, "error", error="One or more files failed")
        else:
            db_set_job_status(job_token, "done")
    except Exception as e:
        db_set_job_status(job_token, "error", error=str(e))

def queue_job(
    app,
    job_token: str,
    saved_paths: list[Path],
    user_id: int | None = None,
    hospital_id: int | None = None,
):
    """
    Submit a job to the shared executor or Celery.
    Refactored to use the new Async Coordinator for ZIPs.
    """
    from utils.celery_helpers import enqueue_task, celery_enabled
    
    if celery_enabled():
        # New Async Workflow: One Coordinator Task per ZIP
        for zip_path in saved_paths:
            enqueue_task(
                "celery_tasks.tasks.zip_upload_tasks.process_zip_coordinator_task",
                str(zip_path),
                job_token,
                user_id=user_id,
                hospital_id=hospital_id,
            )
        return

    # Fallback to local executor (Legacy Synchronous/Threaded)
    executor = app.config["EXECUTOR"]
    executor.submit(process_zip_job, job_token, saved_paths)
