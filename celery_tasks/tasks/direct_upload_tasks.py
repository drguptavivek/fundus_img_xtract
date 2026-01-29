from __future__ import annotations
from pathlib import Path
from celery import chain
from celery.utils.log import get_task_logger
from celery_app import celery_app
from models import Session, DirectImageUpload, BASE_DIR, DIRECT_UPLOAD_DIR
from utils.upload_processing import process_file_visual, process_file_data_pipeline
from job_store import db_set_item_state

logger = get_task_logger(__name__)

@celery_app.task(name="celery_tasks.tasks.direct_upload_tasks.process_direct_upload_thumbnail_task", bind=True, acks_late=True)
def process_direct_upload_thumbnail_task(self, upload_id: int, job_token: str, user_id: int | None = None, hospital_id: int | None = None) -> dict:
    """
    PRIORITY: Thumbnail generation only.
    """
    logger.info(f"Thumbnail task started for upload {upload_id} (user={user_id}, hospital={hospital_id})")
    session = Session()
    filename = "unknown"
    try:
        record = session.query(DirectImageUpload).get(upload_id)
        if not record: raise ValueError(f"DirectImageUpload {upload_id} not found")
        filename, file_path = record.filename, DIRECT_UPLOAD_DIR / record.folder_rel / record.filename
        
        db_set_item_state(job_token, filename, "processing", "Generating thumbnail...")
        process_file_visual(upload_id, 'direct_upload', str(file_path), session)
        db_set_item_state(job_token, filename, "ok", "Thumbnail generated")
        return {"upload_id": upload_id, "file_path": str(file_path), "status": "ok", "user_id": user_id, "hospital_id": hospital_id}
    except Exception as e:
        logger.error(f"Thumbnail failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", f"Thumbnail failed: {str(e)}")
        from celery_job_store import check_and_complete_job
        check_and_complete_job(job_token)
        return {"status": "error", "upload_id": upload_id}
    finally:
        session.close()

@celery_app.task(name="celery_tasks.tasks.direct_upload_tasks.process_direct_data_combined_task", bind=True, acks_late=True)
def process_direct_data_combined_task(self, prev_result: dict, job_token: str) -> None:
    """
    BACKGROUND: Metadata + PII + Strip (Combined optimized pass).
    """
    if prev_result.get("status") != "ok": return
    upload_id, file_path = prev_result["upload_id"], prev_result["file_path"]
    user_id = prev_result.get("user_id")
    hospital_id = prev_result.get("hospital_id")
    
    logger.info(f"Combined data task started for upload {upload_id} (user={user_id}, hospital={hospital_id})")
    session = Session()
    filename = Path(file_path).name
    try:
        db_set_item_state(job_token, filename, "processing", "Extracting metadata & scanning PII...")
        process_file_data_pipeline(upload_id, 'direct_upload', file_path, session, run_metadata=True, run_pii=True, run_strip=True)
        db_set_item_state(job_token, filename, "ok", "Metadata + PII complete")
    except Exception as e:
        logger.error(f"Combined processing failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", f"Processing failed: {e}")
    finally:
        from celery_job_store import check_and_complete_job
        check_and_complete_job(job_token)
        session.close()

@celery_app.task(name="celery_tasks.tasks.direct_upload_tasks.process_direct_metadata_only_task", bind=True, acks_late=True)
def process_direct_metadata_only_task(self, prev_result: dict, job_token: str) -> None:
    """
    BACKGROUND: Metadata + Strip only (No PII).
    """
    if prev_result.get("status") != "ok": return
    upload_id, file_path = prev_result["upload_id"], prev_result["file_path"]
    session = Session()
    filename = Path(file_path).name
    try:
        db_set_item_state(job_token, filename, "processing", "Extracting metadata...")
        process_file_data_pipeline(upload_id, 'direct_upload', file_path, session, run_metadata=True, run_pii=False, run_strip=True)
        db_set_item_state(job_token, filename, "ok", "Ready")
    except Exception as e:
        logger.error(f"Metadata processing failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", f"Metadata failed: {e}")
    finally:
        from celery_job_store import check_and_complete_job
        check_and_complete_job(job_token)
        session.close()

@celery_app.task(name="celery_tasks.tasks.direct_upload_tasks.process_direct_pii_only_task", bind=True, acks_late=True)
def process_direct_pii_only_task(self, prev_result: dict, job_token: str) -> None:
    """
    BACKGROUND: PII scanning only.
    """
    if prev_result.get("status") != "ok": return
    upload_id, file_path = prev_result["upload_id"], prev_result["file_path"]
    session = Session()
    filename = Path(file_path).name
    try:
        db_set_item_state(job_token, filename, "processing", "Scanning for PII...")
        process_file_data_pipeline(upload_id, 'direct_upload', file_path, session, run_metadata=False, run_pii=True, run_strip=False)
        db_set_item_state(job_token, filename, "ok", "Ready")
    except Exception as e:
        logger.error(f"PII scan failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", f"PII failed: {e}")
    finally:
        from celery_job_store import check_and_complete_job
        check_and_complete_job(job_token)
        session.close()
