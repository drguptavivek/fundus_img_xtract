from __future__ import annotations

from pathlib import Path
from celery import chain, chord, group
from celery.utils.log import get_task_logger

from celery_app import celery_app
from models import Session, EncounterFile, EncounterFilePDF
from zip_processor import cleanup_processed_zip_intake_files, ingest_zip_atomic, MaliciousZipError
from utils.log_sanitize import sanitize_log_value
from utils.upload_processing import process_file_visual, process_file_data_pipeline
from utils.fileUtils import get_upload_dirs
from job_store import db_set_job_status, db_set_item_state, db_any_item_error
from celery_job_store import db_add_job_items, check_and_complete_job

logger = get_task_logger(__name__)


@celery_app.task(
    name="celery_tasks.tasks.zip_upload_tasks.cleanup_processed_zip_intake_files",
    bind=True,
    acks_late=True,
)
def cleanup_processed_zip_intake_files_task(
    self,
    date_folder: str | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict:
    """
    Manually archive stale ZIP intake files that are already confirmed ingested.

    The underlying cleanup remains dry-run by default and only moves files after
    confirming the zip_files row, encounter, extracted file rows, and absence of
    active ZIP job items.
    """
    session = Session()
    try:
        result = cleanup_processed_zip_intake_files(
            session,
            date_folder=date_folder,
            dry_run=dry_run,
            limit=limit,
        )
        logger.info(
            "Processed ZIP intake cleanup dry_run=%s date_folder=%s scanned=%s eligible=%s moved=%s skipped=%s errors=%s",
            dry_run,
            sanitize_log_value(date_folder),
            result["scanned"],
            result["eligible"],
            result["moved"],
            result["skipped"],
            result["errors"],
        )
        return result
    finally:
        session.close()

@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_zip_coordinator_task", bind=True, acks_late=True)
def process_zip_coordinator_task(
    self,
    zip_path_str: str,
    job_token: str,
    user_id: int | None = None,
    hospital_id: int | None = None,
    upload_context: dict | None = None,
) -> None:
    """
    Coordinator Task:
    1. Validates & Ingests ZIP (Atomic).
    2. Fans out per-file tasks (Chained).
    """
    zip_path = Path(zip_path_str)
    session = Session()
    
    logger.info(f"Starting ZIP Coordinator for {zip_path.name}")
    db_set_job_status(job_token, "processing")

    try:
        # 1. Atomic Ingestion (Validate + Extract + DB)
        # This moves the ZIP to 'processed' or 'error' automatically
        image_ids, pdf_ids = ingest_zip_atomic(zip_path, session, upload_context=upload_context)
        
        total_files = len(image_ids) + len(pdf_ids)
        logger.info(f"Ingested {total_files} files from {zip_path.name}")
        
        if total_files == 0:
             db_set_job_status(job_token, "done")
             # Mark ZIP item as done (skipped/duplicate)
             db_set_item_state(job_token, zip_path.name, "ok", "Processed (no new files)")
             check_and_complete_job(job_token)
             return

        # Collect new filenames for the Job
        new_filenames = []
        
        # 2. Fan-Out (Chained Tasks)
        for img_id in image_ids:
            file_rec = session.query(EncounterFile).get(img_id)
            if file_rec:
                new_filenames.append(file_rec.filename)
        
        for pdf_id in pdf_ids:
            file_rec = session.query(EncounterFilePDF).get(pdf_id)
            if file_rec:
                new_filenames.append(file_rec.filename)
        
        # Add the extracted files to the JobItem table
        if new_filenames:
            db_add_job_items(job_token, new_filenames)

        # Mark the original ZIP file item as OK (extraction done)
        db_set_item_state(job_token, zip_path.name, "ok", f"Extracted {total_files} files")

        # Now launch tasks for the new items
        thumbnail_tasks = []
        pdf_tasks = []
        for img_id in image_ids:
            file_rec = session.query(EncounterFile).get(img_id)
            if file_rec:
                db_set_item_state(job_token, file_rec.filename, "processing", "Queued for thumbnail generation")
                thumbnail_tasks.append(
                    process_image_thumbnail_task.s(
                        img_id,
                        job_token,
                        user_id=user_id,
                        hospital_id=hospital_id,
                    )
                )

        # For PDFs: OCR only
        for pdf_id in pdf_ids:
            file_rec = session.query(EncounterFilePDF).get(pdf_id)
            if file_rec:
                db_set_item_state(job_token, file_rec.filename, "processing", "Queued for OCR")
                pdf_tasks.append(process_pdf_ocr_task.s(pdf_id, job_token))

        db_set_job_status(job_token, "processing")

        if thumbnail_tasks or pdf_tasks:
            header = group(*(thumbnail_tasks + pdf_tasks))
            if image_ids:
                chord(header)(enqueue_zip_combined_tasks.s(image_ids, job_token, user_id=user_id, hospital_id=hospital_id))
            else:
                header.apply_async()

    except MaliciousZipError as e:
        logger.warning(f"Malicious ZIP rejected: {e}")
        db_set_job_status(job_token, "error", error=f"Malicious ZIP: {str(e)}")
    except Exception as e:
        logger.error(f"ZIP Coordinator Failed: {e}", exc_info=True)
        db_set_job_status(job_token, "error", error=f"Internal processing error: {str(e)}")
    finally:
        session.close()


@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.enqueue_zip_combined_tasks", bind=True, acks_late=True)
def enqueue_zip_combined_tasks(
    self,
    results: list,
    image_ids: list[int],
    job_token: str,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    """Enqueue combined data tasks after all thumbnails + PDF OCR finish."""
    session = Session()
    try:
        for file_id in image_ids:
            record = session.query(EncounterFile).get(file_id)
            if not record:
                continue
            filename = record.filename or "unknown"
            from models import IMAGE_DIR
            if not record.patient_encounter or not record.patient_encounter.zip_file:
                from datetime import datetime
                today_str = datetime.now().strftime("%Y_%m_%d")
            else:
                today_str = record.patient_encounter.zip_file.upload_date.strftime("%Y_%m_%d")

            file_path = IMAGE_DIR / today_str / filename
            prev_result = {
                "file_id": file_id,
                "file_type": "encounter_file",
                "file_path": str(file_path),
                "status": "ok",
                "user_id": user_id,
                "hospital_id": hospital_id,
            }
            process_zip_data_combined_task.delay(prev_result, "encounter_file", job_token)
    finally:
        session.close()


@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_image_thumbnail_task", bind=True, acks_late=True)
def process_image_thumbnail_task(
    self,
    file_id: int,
    job_token: str,
    user_id: int | None = None,
    hospital_id: int | None = None
) -> dict:
    """
    Phase 1a: Image Thumbnail Task.
    """
    logger.info(f"ZIP Thumbnail task started for file {file_id} (user={user_id}, hospital={hospital_id})")
    session = Session()
    filename = "unknown"
    try:
        record = session.query(EncounterFile).get(file_id)
        if not record:
            raise ValueError(f"EncounterFile {file_id} not found")
            
        filename = record.filename
        
        from models import IMAGE_DIR
        if not record.patient_encounter or not record.patient_encounter.zip_file:
             from datetime import datetime
             today_str = datetime.now().strftime("%Y_%m_%d")
        else:
             today_str = record.patient_encounter.zip_file.upload_date.strftime("%Y_%m_%d")

        file_path = IMAGE_DIR / today_str / filename
        
        if not file_path.exists():
             raise FileNotFoundError(f"Image not found at {file_path}")

        db_set_item_state(job_token, filename, "processing", "Generating thumbnail...")
        process_file_visual(file_id, 'encounter_file', str(file_path), session)
        db_set_item_state(job_token, filename, "ok", "Thumbnail generated")
        return {
            "file_id": file_id,
            "file_type": "encounter_file",
            "file_path": str(file_path),
            "status": "ok",
            "user_id": user_id,
            "hospital_id": hospital_id
        }

    except Exception as e:
        logger.error(f"Thumbnail Task Failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", str(e))
        check_and_complete_job(job_token) 
        return {"status": "error", "file_id": file_id}
    finally:
        session.close()


@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_pdf_ocr_task", bind=True, acks_late=True)
def process_pdf_ocr_task(
    self,
    file_id: int,
    job_token: str
) -> dict:
    """
    Phase 1b: PDF OCR Task.
    """
    session = Session()
    filename = "unknown"
    try:
        record = session.query(EncounterFilePDF).get(file_id)
        if not record:
            raise ValueError(f"EncounterFilePDF {file_id} not found")

        filename = record.filename
        from models import PDF_DIR
        if not record.patient_encounter or not record.patient_encounter.zip_file:
             from datetime import datetime
             today_str = datetime.now().strftime("%Y_%m_%d")
        else:
             today_str = record.patient_encounter.zip_file.upload_date.strftime("%Y_%m_%d")

        file_path = PDF_DIR / today_str / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found at {file_path}")

        from process_pdfs import process_all_pdfs_for_ocr
        process_all_pdfs_for_ocr(limit_filenames={filename})
        
        db_set_item_state(job_token, filename, "ok", "OCR Complete")
        
        return {
            "file_id": file_id,
            "file_type": "encounter_file_pdf",
            "file_path": str(file_path),
            "status": "ok"
        }
        
    except Exception as e:
        logger.error(f"OCR Task Failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", str(e))
        return {"status": "error", "file_id": file_id}
    finally:
        check_and_complete_job(job_token)
        session.close()

@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_zip_data_combined_task", bind=True, acks_late=True)

def process_zip_data_combined_task(

    self,

    prev_result: dict,

    file_type: str,

    job_token: str

) -> None:

    """

    BACKGROUND: Metadata + PII + Strip (Combined optimized pass) for ZIP items.

    """

    if prev_result.get("status") != "ok":

        check_and_complete_job(job_token)

        return 



    file_id, file_path = prev_result["file_id"], prev_result["file_path"]

    user_id = prev_result.get("user_id")

    hospital_id = prev_result.get("hospital_id")

    

    logger.info(f"ZIP Combined data task started for file {file_id} (user={user_id}, hospital={hospital_id})")
    session = Session()
    filename = Path(file_path).name
    try:
        if file_type == 'encounter_file':
            db_set_item_state(job_token, filename, "processing", "Extracting metadata & scanning PII...")
            process_file_data_pipeline(file_id, 'encounter_file', file_path, session, run_metadata=True, run_pii=True, run_strip=True)
            db_set_item_state(job_token, filename, "ok", "Metadata + PII complete")
        else:
            db_set_item_state(job_token, filename, "ok", "Ready")
    except Exception as e:
        logger.error(f"ZIP Combined processing failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", str(e))
    finally:
        check_and_complete_job(job_token)
        session.close()
