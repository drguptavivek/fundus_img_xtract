"""
Thumbnail generation job system.

This module provides async thumbnail generation using the existing Job/JobItem
infrastructure. It handles both direct uploads and ZIP upload images.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum

from models import (
    DirectImageUpload, EncounterFile, PatientEncounters, Job, JobItem,
    Session, DirectImageVerify
)
from db_transaction_manager import transaction_scope
from job_store import db_set_job_status, db_set_item_state, db_any_item_error
from utils.image_processing import generate_thumbnail, get_thumbnail_filename
from utils.fileUtils import (
    get_thumbnail_path_direct, get_thumbnail_path_encounter,
    abs_from_parts, IMAGE_DIR
)

# Configure logger
logger = logging.getLogger(__name__)


def with_app_context(app, func):
    """
    Wrapper to ensure function runs within Flask application context.

    This wrapper solves the "Working outside of application context" error
    by ensuring that background threads have access to Flask's current_app
    and other context-bound functionality.

    Args:
        app: Flask application instance
        func: Function to wrap with application context

    Returns:
        Wrapped function that will execute within Flask app context
    """
    def wrapper(*args, **kwargs):
        with app.app_context():
            return func(*args, **kwargs)
    return wrapper

# Job types for thumbnail generation
class ThumbnailJobType(Enum):
    DIRECT_ORIGINAL = "thumbnail_direct_original"
    DIRECT_EDITED = "thumbnail_direct_edited"
    ENCOUNTER = "thumbnail_encounter"
    BATCH_EXISTING = "thumbnail_batch_existing"

# Job states
class JobState(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    SKIPPED = "skipped"


def create_thumbnail_job(
    job_type: ThumbnailJobType,
    image_references: List[Dict[str, Any]],
    uploader_user_id: Optional[int] = None,
    uploader_username: Optional[str] = None,
    uploader_ip: Optional[str] = None,
    lab_unit_id: Optional[int] = None
) -> Optional[str]:
    """
    Create a thumbnail generation job.

    Args:
        job_type: Type of thumbnail job
        image_references: List of image references with metadata
        uploader_user_id: User ID who triggered the job
        uploader_username: Username who triggered the job
        uploader_ip: IP address of uploader
        lab_unit_id: Lab unit ID for scoping

    Returns:
        Job token if created successfully, None otherwise
    """
    try:
        filenames = []
        rejected = []

        for ref in image_references:
            # Validate image reference
            if not _validate_image_reference(ref, job_type):
                rejected.append(f"Invalid reference: {ref}")
                continue

            # Create filename for job item
            filename = _create_job_item_filename(ref, job_type)
            if filename:
                filenames.append(filename)

        if not filenames:
            logger.warning(f"No valid image references for thumbnail job type {job_type.value}")
            return None

        # Create job using existing job_store pattern
        from job_store import db_create_job
        job_token = db_create_job(
            filenames=filenames,
            rejected=rejected,
            uploader_user_id=uploader_user_id,
            uploader_username=uploader_username,
            uploader_ip=uploader_ip,
            lab_unit_id=lab_unit_id,
            upload_type=job_type.value
        )

        # Store detailed image reference data for processing
        _store_job_image_references(job_token, image_references, job_type)

        logger.info(f"Created thumbnail job {job_token} with {len(filenames)} items")
        return job_token

    except Exception as e:
        logger.error(f"Failed to create thumbnail job: {str(e)}")
        return None


def _validate_image_reference(ref: Dict[str, Any], job_type: ThumbnailJobType) -> bool:
    """Validate an image reference based on job type."""
    if not isinstance(ref, dict):
        return False

    if job_type == ThumbnailJobType.DIRECT_ORIGINAL:
        return all(key in ref for key in ['image_id', 'folder_rel', 'filename'])
    elif job_type == ThumbnailJobType.DIRECT_EDITED:
        return all(key in ref for key in ['image_id', 'folder_rel', 'edited_filename'])
    elif job_type == ThumbnailJobType.ENCOUNTER:
        return 'image_id' in ref
    else:
        return False


def _create_job_item_filename(ref: Dict[str, Any], job_type: ThumbnailJobType) -> Optional[str]:
    """Create a filename for job item tracking."""
    if job_type == ThumbnailJobType.DIRECT_ORIGINAL:
        return f"direct_orig_{ref['image_id']}_{ref['filename']}"
    elif job_type == ThumbnailJobType.DIRECT_EDITED:
        return f"direct_edited_{ref['image_id']}_{ref['edited_filename']}"
    elif job_type == ThumbnailJobType.ENCOUNTER:
        return f"encounter_{ref['image_id']}"
    else:
        return None


def _store_job_image_references(job_token: str, image_references: List[Dict[str, Any]], job_type: ThumbnailJobType):
    """Store detailed image reference data in job detail field."""
    try:
        with transaction_scope() as db:
            job = db.query(Job).filter_by(token=job_token).first()
            if job:
                # Store reference data as JSON in rejected_summary (temporary storage)
                import json
                ref_data = {
                    'job_type': job_type.value,
                    'image_references': image_references,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
                job.rejected_summary = json.dumps(ref_data)
                db.add(job)
    except Exception as e:
        logger.error(f"Failed to store job image references: {str(e)}")


def _load_job_image_references(job_token: str) -> Optional[Dict[str, Any]]:
    """Load image reference data from job detail field."""
    try:
        with transaction_scope() as db:
            job = db.query(Job).filter_by(token=job_token).first()
            if job and job.rejected_summary:
                import json
                return json.loads(job.rejected_summary)
    except Exception as e:
        logger.error(f"Failed to load job image references: {str(e)}")
    return None


def process_thumbnail_job(job_token: str):
    """
    Process a thumbnail generation job.

    This is the main worker function that processes all items in a thumbnail job.
    """
    logger.info(f"Starting thumbnail job processing: {job_token}")
    db_set_job_status(job_token, JobState.PROCESSING.value)

    try:
        # Load job image references
        job_data = _load_job_image_references(job_token)
        if not job_data:
            raise ValueError("No image reference data found for job")

        job_type = ThumbnailJobType(job_data['job_type'])
        image_references = job_data['image_references']

        # Process each image reference
        for ref in image_references:
            try:
                _process_single_thumbnail(job_token, ref, job_type)
            except Exception as e:
                filename = _create_job_item_filename(ref, job_type) or "unknown"
                logger.error(f"Failed to process thumbnail for {filename}: {str(e)}")
                db_set_item_state(job_token, filename, JobState.ERROR.value, str(e))

        # Check final job status
        if db_any_item_error(job_token):
            db_set_job_status(job_token, JobState.ERROR.value, error="Some thumbnails failed to generate")
        else:
            db_set_job_status(job_token, JobState.COMPLETED.value)

        logger.info(f"Completed thumbnail job processing: {job_token}")

    except Exception as e:
        logger.error(f"Thumbnail job failed: {job_token} - {str(e)}")
        db_set_job_status(job_token, JobState.ERROR.value, error=str(e))


def _process_single_thumbnail(job_token: str, ref: Dict[str, Any], job_type: ThumbnailJobType):
    """Process a single thumbnail generation."""
    filename = _create_job_item_filename(ref, job_type)
    if not filename:
        raise ValueError("Could not create job item filename")

    try:
        # Set item to processing
        db_set_item_state(job_token, filename, JobState.PROCESSING.value)

        # Generate thumbnail based on job type
        success = False
        message = ""

        if job_type == ThumbnailJobType.DIRECT_ORIGINAL:
            success, message = _generate_direct_thumbnail(ref, kind="orig")
        elif job_type == ThumbnailJobType.DIRECT_EDITED:
            success, message = _generate_direct_thumbnail(ref, kind="edited")
        elif job_type == ThumbnailJobType.ENCOUNTER:
            success, message = _generate_encounter_thumbnail(ref)

        # Update item status
        if success:
            db_set_item_state(job_token, filename, JobState.COMPLETED.value, message)

            # Update database record with thumbnail filename
            _update_thumbnail_record(ref, job_type)
        else:
            db_set_item_state(job_token, filename, JobState.ERROR.value, message or "Thumbnail generation failed")

    except Exception as e:
        db_set_item_state(job_token, filename, JobState.ERROR.value, str(e))
        raise


def _generate_direct_thumbnail(ref: Dict[str, Any], kind: str = "orig") -> tuple[bool, str]:
    """Generate thumbnail for direct upload image."""
    try:
        folder_rel = ref['folder_rel']

        if kind == "orig":
            original_filename = ref['filename']
        else:  # edited
            original_filename = ref['edited_filename']

        # Get absolute path to source image
        source_path = abs_from_parts(folder_rel, original_filename, kind)
        if not source_path.exists():
            return False, f"Source image not found: {source_path}"

        # Generate thumbnail path
        thumbnail_path = get_thumbnail_path_direct(folder_rel, original_filename, kind)

        # Generate thumbnail
        success = generate_thumbnail(source_path, thumbnail_path)
        if success:
            return True, f"Thumbnail generated: {thumbnail_path.name}"
        else:
            return False, "Thumbnail generation failed"

    except Exception as e:
        return False, str(e)


def _generate_encounter_thumbnail(ref: Dict[str, Any]) -> tuple[bool, str]:
    """Generate thumbnail for encounter file (ZIP upload)."""
    try:
        image_id = ref['image_id']

        # Get encounter file from database
        with transaction_scope() as db:
            encounter_file = db.query(EncounterFile).filter_by(id=image_id).first()
            if not encounter_file:
                return False, f"Encounter file not found: {image_id}"

            # Get absolute path to source image
            source_path = IMAGE_DIR / encounter_file.filename
            if not source_path.exists():
                return False, f"Source image not found: {source_path}"

            # Generate thumbnail path
            thumbnail_path = get_thumbnail_path_encounter(source_path)

            # Generate thumbnail
            success = generate_thumbnail(source_path, thumbnail_path)
            if success:
                return True, f"Thumbnail generated: {thumbnail_path.name}"
            else:
                return False, "Thumbnail generation failed"

    except Exception as e:
        return False, str(e)


def _update_thumbnail_record(ref: Dict[str, Any], job_type: ThumbnailJobType):
    """Update database record with thumbnail filename."""
    try:
        with transaction_scope() as db:
            if job_type in [ThumbnailJobType.DIRECT_ORIGINAL, ThumbnailJobType.DIRECT_EDITED]:
                # Update DirectImageUpload record
                image_id = ref['image_id']
                direct_upload = db.query(DirectImageUpload).filter_by(id=image_id).first()
                if direct_upload:
                    if job_type == ThumbnailJobType.DIRECT_ORIGINAL:
                        original_filename = ref['filename']
                        thumbnail_filename = get_thumbnail_filename(original_filename)
                        direct_upload.thumbnail_filename = thumbnail_filename
                    else:  # edited
                        edited_filename = ref['edited_filename']
                        thumbnail_filename = get_thumbnail_filename(edited_filename)
                        direct_upload.edited_thumbnail_filename = thumbnail_filename
                    db.add(direct_upload)

            elif job_type == ThumbnailJobType.ENCOUNTER:
                # Update EncounterFile record
                image_id = ref['image_id']
                encounter_file = db.query(EncounterFile).filter_by(id=image_id).first()
                if encounter_file:
                    thumbnail_filename = get_thumbnail_filename(encounter_file.filename)
                    encounter_file.thumbnail_filename = thumbnail_filename
                    db.add(encounter_file)

    except Exception as e:
        logger.error(f"Failed to update thumbnail record: {str(e)}")


def queue_thumbnail_job(job_token: str, app):
    """
    Queue a thumbnail job for processing.

    Args:
        job_token: Token for the thumbnail job
        app: Flask application instance (for executor)
    """
    try:
        executor = app.config.get("EXECUTOR")
        if not executor:
            raise ValueError("No executor found in app config")

        # Use context wrapper to ensure Flask app context is available
        # in background threads, preventing "Working outside of application context" errors
        wrapped_process_thumbnail_job = with_app_context(app, process_thumbnail_job)
        executor.submit(wrapped_process_thumbnail_job, job_token)
        logger.info(f"Queued thumbnail job for processing: {job_token}")

    except Exception as e:
        logger.error(f"Failed to queue thumbnail job {job_token}: {str(e)}")
        db_set_job_status(job_token, JobState.ERROR.value, error=f"Failed to queue job: {str(e)}")


def schedule_direct_upload_thumbnails(direct_upload_id: int, app, user_context: Optional[Dict[str, Any]] = None):
    """
    Schedule thumbnail generation for a direct upload image.

    Args:
        direct_upload_id: ID of the DirectImageUpload record
        app: Flask application instance
        user_context: User context dict (user_id, username, ip)
    """
    try:
        with transaction_scope() as db:
            direct_upload = db.query(DirectImageUpload).filter_by(id=direct_upload_id).first()
            if not direct_upload:
                raise ValueError(f"Direct upload not found: {direct_upload_id}")

            user_context = user_context or {}
            image_references = []

            # Schedule original image thumbnail
            if direct_upload.filename:
                image_references.append({
                    'image_id': direct_upload.id,
                    'folder_rel': direct_upload.folder_rel,
                    'filename': direct_upload.filename
                })

            # Schedule edited image thumbnail if it exists
            if direct_upload.edited_filename:
                image_references.append({
                    'image_id': direct_upload.id,
                    'folder_rel': direct_upload.folder_rel,
                    'edited_filename': direct_upload.edited_filename
                })

            if not image_references:
                logger.warning(f"No images to generate thumbnails for direct upload {direct_upload_id}")
                return

            # Create and queue job
            job_token = create_thumbnail_job(
                ThumbnailJobType.DIRECT_ORIGINAL if len(image_references) == 1 else ThumbnailJobType.DIRECT_EDITED,
                image_references,
                uploader_user_id=user_context.get('user_id', direct_upload.uploader_id),
                uploader_username=user_context.get('username', direct_upload.uploader.username if direct_upload.uploader else None),
                uploader_ip=user_context.get('ip'),
                lab_unit_id=direct_upload.lab_unit_id
            )

            if job_token:
                queue_thumbnail_job(job_token, app)
                logger.info(f"Scheduled thumbnails for direct upload {direct_upload_id}: job {job_token}")
            else:
                logger.error(f"Failed to create thumbnail job for direct upload {direct_upload_id}")

    except Exception as e:
        logger.error(f"Failed to schedule thumbnails for direct upload {direct_upload_id}: {str(e)}")


def schedule_encounter_thumbnails(encounter_file_ids: List[int], app, user_context: Optional[Dict[str, Any]] = None):
    """
    Schedule thumbnail generation for encounter files.

    Args:
        encounter_file_ids: List of EncounterFile IDs
        app: Flask application instance
        user_context: User context dict (user_id, username, ip)
    """
    try:
        if not encounter_file_ids:
            return

        with transaction_scope() as db:
            encounter_files = db.query(EncounterFile).filter(
                EncounterFile.id.in_(encounter_file_ids)
            ).all()

            image_references = []
            lab_unit_id = None

            for ef in encounter_files:
                image_references.append({
                    'image_id': ef.id,
                })
                if not lab_unit_id:
                    lab_unit_id = ef.lab_unit_id

            if not image_references:
                logger.warning("No valid encounter files for thumbnail generation")
                return

            user_context = user_context or {}

            # Create and queue job
            job_token = create_thumbnail_job(
                ThumbnailJobType.ENCOUNTER,
                image_references,
                uploader_user_id=user_context.get('user_id'),
                uploader_username=user_context.get('username'),
                uploader_ip=user_context.get('ip'),
                lab_unit_id=lab_unit_id
            )

            if job_token:
                queue_thumbnail_job(job_token, app)
                logger.info(f"Scheduled thumbnails for {len(encounter_file_ids)} encounter files: job {job_token}")
            else:
                logger.error(f"Failed to create thumbnail job for encounter files")

    except Exception as e:
        logger.error(f"Failed to schedule thumbnails for encounter files: {str(e)}")


def get_thumbnail_job_status(job_token: str) -> Optional[Dict[str, Any]]:
    """
    Get status of a thumbnail generation job.

    Args:
        job_token: Token for the thumbnail job

    Returns:
        Job status dict or None if not found
    """
    try:
        from job_store import db_get_job_payload
        return db_get_job_payload(job_token)
    except Exception as e:
        logger.error(f"Failed to get thumbnail job status {job_token}: {str(e)}")
        return None


# Utility functions for integration
def create_user_context(user_id: int, username: str, ip: str) -> Dict[str, Any]:
    """Create a user context dict for job tracking."""
    return {
        'user_id': user_id,
        'username': username,
        'ip': ip
    }