from __future__ import annotations

from pathlib import Path
from celery import chain
from celery.utils.log import get_task_logger

from celery_app import celery_app
from models import Session, EncounterFile, EncounterFilePDF
from zip_processor import ingest_zip_atomic, MaliciousZipError
from utils.upload_processing import process_file_visual, process_file_metadata_strip
from utils.fileUtils import get_upload_dirs
from job_store import db_set_job_status, db_set_item_state, db_any_item_error
from celery_job_store import db_add_job_items, check_and_complete_job

logger = get_task_logger(__name__)

@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_zip_coordinator_task", bind=True, acks_late=True)
def process_zip_coordinator_task(
    self,
    zip_path_str: str,
    job_token: str,
    user_id: int | None = None,
    hospital_id: int | None = None,
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
        image_ids, pdf_ids = ingest_zip_atomic(zip_path, session)
        
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
        # For Images: Visual (Thumbnail) -> Metadata+Strip
        for img_id in image_ids:
            # Update item state to 'processing'
            file_rec = session.query(EncounterFile).get(img_id)
            if file_rec:
                new_filenames.append(file_rec.filename)
        
        for pdf_id in pdf_ids:
            file_rec = session.query(EncounterFilePDF).get(pdf_id)
            if file_rec:
                new_filenames.append(file_rec.filename)
        
        # Add the extracted files to the JobItem table so we can track their progress
        if new_filenames:
            db_add_job_items(job_token, new_filenames)

        # Mark the original ZIP file item as OK (extraction done)
        db_set_item_state(job_token, zip_path.name, "ok", f"Extracted {total_files} files")

        # Now launch tasks for the new items
        for img_id in image_ids:
            file_rec = session.query(EncounterFile).get(img_id)
            if file_rec:
                db_set_item_state(job_token, file_rec.filename, "processing", "Queued for thumbnail generation")
                
                # Chain: Thumbnail -> Metadata
                chain(
                    process_image_thumbnail_task.s(img_id, job_token),
                    process_file_metadata_strip_task.s('encounter_file', job_token)
                ).apply_async()

        # For PDFs: OCR only (No metadata strip chain yet)
        for pdf_id in pdf_ids:
            file_rec = session.query(EncounterFilePDF).get(pdf_id)
            if file_rec:
                db_set_item_state(job_token, file_rec.filename, "processing", "Queued for OCR")

                # PDF Task
                process_pdf_ocr_task.delay(pdf_id, job_token)

        # Mark job as "processing" (it will be marked done by a monitoring task or we assume done when submitted?)
        db_set_job_status(job_token, "processing")

    except MaliciousZipError as e:
        logger.warning(f"Malicious ZIP rejected: {e}")
        db_set_job_status(job_token, "error", error=f"Malicious ZIP: {str(e)}")
    except Exception as e:
        logger.error(f"ZIP Coordinator Failed: {e}", exc_info=True)
        db_set_job_status(job_token, "error", error=f"Internal processing error: {str(e)}")
    finally:
        session.close()


@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_image_thumbnail_task", bind=True, acks_late=True)
def process_image_thumbnail_task(
    self,
    file_id: int,
    job_token: str
) -> dict:
    """
    Phase 1a: Image Thumbnail Task.
    Expected to run on 'thumbnails' queue.
    """
    session = Session()
    filename = "unknown"
    try:
        record = session.query(EncounterFile).get(file_id)
        if not record:
            raise ValueError(f"EncounterFile {file_id} not found")
            
        filename = record.filename
        
        # Locate file (assuming daily structure)
        from models import IMAGE_DIR
        # record.patient_encounter.zip_file.upload_date corresponds to the folder date
        if not record.patient_encounter or not record.patient_encounter.zip_file:
             # Fallback if links missing (shouldn't happen for valid zips)
             today_str = datetime.now().strftime("%Y_%m_%d")
        else:
             today_str = record.patient_encounter.zip_file.upload_date.strftime("%Y_%m_%d")

        file_path = IMAGE_DIR / today_str / filename
        
        # Fallback search if date changed (unlikely for immediate task)
        if not file_path.exists():
             # Try just the filename in IMAGE_DIR (if structure differs)
             # or look in recent folders? 
             # For now, strict check.
             raise FileNotFoundError(f"Image not found at {file_path}")

        # Process
        result = process_file_visual(file_id, 'encounter_file', str(file_path), session)
        
        if result.get("status") == "ok":
            db_set_item_state(job_token, filename, "processing", "Thumbnail generated")
        else:
            db_set_item_state(job_token, filename, "error", result.get("error"))

        return {
            "file_id": file_id,
            "file_type": "encounter_file",
            "file_path": str(file_path),
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"Thumbnail Task Failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", str(e))
        # Ensure we check completion even on failure, as this might be terminal for this chain
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
    Expected to run on 'zip_ocr' queue.
    """
    session = Session()
    filename = "unknown"
    try:
        record = session.query(EncounterFilePDF).get(file_id)
        if not record:
            raise ValueError(f"EncounterFilePDF {file_id} not found")

        filename = record.filename
        
        # Locate file
        from models import PDF_DIR
        # record.patient_encounter.zip_file.upload_date corresponds to the folder date
        if not record.patient_encounter or not record.patient_encounter.zip_file:
             today_str = datetime.now().strftime("%Y_%m_%d")
        else:
             today_str = record.patient_encounter.zip_file.upload_date.strftime("%Y_%m_%d")

        file_path = PDF_DIR / today_str / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found at {file_path}")

        # Run OCR
        from process_pdfs import process_all_pdfs_for_ocr
        # This function handles DB update internally
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
        # Terminal task for PDF: Check if job is complete
        check_and_complete_job(job_token)
        session.close()


@celery_app.task(name="celery_tasks.tasks.zip_upload_tasks.process_file_metadata_strip_task", bind=True, acks_late=True)
def process_file_metadata_strip_task(
    self,
    prev_result: dict, # Result from previous task in chain
    file_type: str,
    job_token: str
) -> None:
    """
    Phase 2: Metadata + Strip
    """
    if prev_result.get("status") != "ok":
        # Previous step failed, so this chain branch is dead.
        # We must check completion here because this task was *expected* to run.
        # Actually, if prev failed, it might not even call this task if using immutable signatures?
        # But 'chain' usually calls next.
        # If prev returned {"status": "error"}, we enter here.
        check_and_complete_job(job_token)
        return 

    file_id = prev_result["file_id"]
    file_path = prev_result["file_path"]
    
    # We trust the file_type passed in args match what we expect (Images only typically)
    # If PDF comes here, we might skip stripping.

    session = Session()
    filename = Path(file_path).name
    try:
         # Only strip/metadata for Images for now
         if file_type == 'encounter_file':
             db_set_item_state(job_token, filename, "processing", "Extracting metadata...")
             
             result = process_file_metadata_strip(file_id, 'encounter_file', file_path, session)
             
             if result.get("status") == "ok":
                 db_set_item_state(job_token, filename, "ok", "Ready")
             else:
                 db_set_item_state(job_token, filename, "error", result.get("message"))
         
         else:
             # Just mark done for others if they reached here
             db_set_item_state(job_token, filename, "ok", "Ready")

    except Exception as e:
        logger.error(f"Metadata Task Failed for {filename}: {e}", exc_info=True)
        db_set_item_state(job_token, filename, "error", str(e))
    finally:
        # Terminal task for Images: Check if job is complete
        check_and_complete_job(job_token)
        session.close()
