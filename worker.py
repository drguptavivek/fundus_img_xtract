# worker.py
from pathlib import Path
from flask import current_app
from models import Session
from main import setup_environment, setup_database, process_zip_file
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
    setup_database()
    db = Session()
    try:
        pdfs = process_zip_file(zip_path, db)
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

def _job_worker(job_token: str, saved_paths: list[Path]):
    db_set_job_status(job_token, "processing")
    try:
        for p in saved_paths:
            db_set_item_state(job_token, p.name, "processing")
            result = _process_one_zip(p)
            db_set_item_state(job_token, p.name, result["status"], result.get("message"))
        if db_any_item_error(job_token):
            db_set_job_status(job_token, "error", error="One or more files failed")
        else:
            db_set_job_status(job_token, "done")
    except Exception as e:
        db_set_job_status(job_token, "error", error=str(e))

def queue_job(app, job_token: str, saved_paths: list[Path]):
    """
    Submit a job to the shared executor (ThreadPoolExecutor stored in app.config).
    """
    executor = app.config["EXECUTOR"]
    executor.submit(_job_worker, job_token, saved_paths)
