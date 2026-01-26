from __future__ import annotations
from pathlib import Path
from celery import chain
from celery.utils.log import get_task_logger
from celery_app import celery_app
from models import Session, DirectImageUpload, BASE_DIR
from utils.upload_processing import process_file_visual, process_file_metadata_strip
from job_store import db_set_item_state

logger = get_task_logger(__name__)

@celery_app.task(name="celery_tasks.tasks.direct_upload_tasks.process_direct_upload_file_task", bind=True, acks_late=True)
def process_direct_upload_file_task(self, upload_id: int, job_token: str) -> dict:
    """
    Phase 1: Visual & Metadata Processing for Direct Upload.
    - Generates Thumbnail
    - Extracts Metadata
    - Strips EXIF
    """
    session = Session()
    filename = "unknown"
    try:
        record = session.query(DirectImageUpload).get(upload_id)
        if not record:
            raise ValueError(f"DirectImageUpload {upload_id} not found")
        
        filename = record.filename
        
        # Resolve full path
        # Direct uploads use folder_rel to store relative path from 'files' dir
        file_path = BASE_DIR / "files" / record.folder_rel / record.filename
        
        if not file_path.exists():
             raise FileNotFoundError(f"File not found at {file_path}")

        # 1. Visual (Thumbnail)
        db_set_item_state(job_token, filename, "processing", "Generating thumbnail...")
        vis_res = process_file_visual(upload_id, 'direct_upload', str(file_path), session)
        if vis_res.get("status") != "ok":
             logger.warning(f"Thumbnail generation warning for {filename}: {vis_res.get('error')}")

        # 2. Metadata & Strip
        db_set_item_state(job_token, filename, "processing", "Extracting metadata...")
        meta_res = process_file_metadata_strip(upload_id, 'direct_upload', str(file_path), session)
        if meta_res.get("status") != "ok":
             raise Exception(meta_res.get("message"))

        db_set_item_state(job_token, filename, "processing", "Scanning for PII...")
        
        return {
            "upload_id": upload_id,
            "file_path": str(file_path),
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"Direct Upload Task Failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", str(e))
        from celery_job_store import check_and_complete_job
        check_and_complete_job(job_token)
        return {"status": "error", "upload_id": upload_id}
    finally:
        session.close()

@celery_app.task(name="celery_tasks.tasks.direct_upload_tasks.process_direct_pii_task", bind=True, acks_late=True)
def process_direct_pii_task(self, prev_result: dict, job_token: str) -> None:
    """
    Phase 2: PII Detection
    """
    if prev_result.get("status") != "ok":
        return

    upload_id = prev_result["upload_id"]
    file_path = prev_result["file_path"]
    
    session = Session()
    filename = Path(file_path).name
    
    try:
        record = session.query(DirectImageUpload).get(upload_id)
        if not record:
             return

        # Run PII Detection
        # We reuse run_pii_detection_for_path which updates DB
        from utils.pii_verification import run_pii_detection_for_path
        
        # We use 'orig' variant as we are scanning the main file (even if stripped)
        run_pii_detection_for_path(
            session,
            image_uuid=str(record.uuid),
            image_variant="orig",
            image_path=file_path
        )
        session.commit()
        
        db_set_item_state(job_token, filename, "ok", "Ready")

    except Exception as e:
        logger.error(f"PII Task Failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", f"PII Check Failed: {e}")
    finally:
        from celery_job_store import check_and_complete_job
        check_and_complete_job(job_token)
        session.close()
