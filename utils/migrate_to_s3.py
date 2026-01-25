"""
S3 Migration Utilities

Migrate local files to S3 with proper error handling and rollback.

Features:
- Transaction guards with automatic rollback
- Batch migration support
- Progress tracking
- Local file deletion (optional)
"""

import logging
from pathlib import Path
from contextlib import contextmanager
from typing import List, Tuple

from sqlalchemy.exc import SQLAlchemyError

from utils.storage_backends import S3StorageBackend, StorageError
from utils.log_sanitize import sanitize_log_value
from db_transaction_manager import db

logger = logging.getLogger('s3.migration')


@contextmanager
def s3_migration_guard(s3_config_id: int):
    """
    Context manager that handles rollback of S3 migrations on failure.
    Tracks uploaded S3 keys and deletes them if the transaction fails.

    Args:
        s3_config_id: S3 config ID to use for migration

    Yields:
        Tuple of (s3_backend, uploaded_keys_list)

    Example:
        with s3_migration_guard(config_id) as (backend, uploaded_keys):
            backend.save_file(path, key)
            uploaded_keys.append(key)
            # ... more uploads ...
            # Commit happens automatically if no exception
    """
    from models import S3Config

    uploaded_keys = []  # Track what we uploaded
    backend = None

    try:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            raise ValueError(f"S3 config {s3_config_id} not found")

        backend = S3StorageBackend(s3_config)

        yield backend, uploaded_keys

        # If we get here, everything succeeded - commit the DB transaction
        db.commit()

    except Exception as e:
        # Rollback: Delete any files we uploaded to S3
        if uploaded_keys and backend:
            logger.warning(f"Migration failed, rolling back {len(uploaded_keys)} S3 uploads")
            for key in uploaded_keys:
                try:
                    backend.delete(key)
                    logger.info(f"Rolled back S3 upload: {key}")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback S3 key {key}: {rollback_error}")

        # Rollback DB transaction
        db.rollback()
        raise StorageError(f"Migration failed and rolled back: {e}")


def migrate_direct_upload_to_s3(upload_id: int, s3_config_id: int) -> bool:
    """
    Migrate a DirectImageUpload from local to S3 with proper rollback.

    Args:
        upload_id: DirectImageUpload ID
        s3_config_id: S3 config ID to use

    Returns:
        True on success

    Raises:
        StorageError: If migration fails
    """
    from models import DirectImageUpload
    from app import BASE_DIR

    with s3_migration_guard(s3_config_id) as (backend, uploaded_keys):
        upload = db.query(DirectImageUpload).get(upload_id)
        if not upload:
            raise ValueError(f"DirectImageUpload {upload_id} not found")

        # 1. Upload original to S3
        original_path = BASE_DIR / upload.folder_rel / upload.filename
        if original_path.exists():
            s3_key_original = f"direct_uploads/{upload.uuid}/{upload.filename}"
            backend.save_file(original_path, s3_key_original)
            uploaded_keys.append(s3_key_original)
            upload.s3_object_key = s3_key_original
        else:
            raise StorageError(f"Original file not found: {original_path}")

        # 2. Upload edited if exists
        if upload.edited_filename:
            edited_path = BASE_DIR / upload.folder_rel / "edited" / upload.edited_filename
            if edited_path.exists():
                s3_key_edited = f"direct_uploads/{upload.uuid}/edited/{upload.edited_filename}"
                backend.save_file(edited_path, s3_key_edited)
                uploaded_keys.append(s3_key_edited)
                upload.s3_object_key_edited = s3_key_edited

        # 3. Upload thumbnails if exist
        if upload.thumbnail_filename:
            thumb_path = BASE_DIR / upload.folder_rel / upload.thumbnail_filename
            if thumb_path.exists():
                s3_key_thumb = f"direct_uploads/{upload.uuid}/thumbnails/{upload.thumbnail_filename}"
                backend.save_file(thumb_path, s3_key_thumb)
                uploaded_keys.append(s3_key_thumb)
                upload.s3_object_key_thumbnail = s3_key_thumb

        if upload.edited_thumbnail_filename:
            thumb_edited_path = BASE_DIR / upload.folder_rel / upload.edited_thumbnail_filename
            if thumb_edited_path.exists():
                s3_key_thumb_edited = f"direct_uploads/{upload.uuid}/thumbnails/{upload.edited_thumbnail_filename}"
                backend.save_file(thumb_edited_path, s3_key_thumb_edited)
                uploaded_keys.append(s3_key_thumb_edited)
                upload.s3_object_key_edited_thumbnail = s3_key_thumb_edited

        # 4. Update DB (will be committed by context manager)
        upload.s3_config_id = s3_config_id

        logger.info(f"Successfully migrated DirectImageUpload {upload_id} to S3 config {s3_config_id}")
        return True


def migrate_encounter_file_to_s3(file_id: int, s3_config_id: int) -> bool:
    """
    Migrate an EncounterFile from local to S3.

    Args:
        file_id: EncounterFile ID
        s3_config_id: S3 config ID to use

    Returns:
        True on success

    Raises:
        StorageError: If migration fails
    """
    from models import EncounterFile, PatientEncounters
    from app import IMAGE_DIR

    with s3_migration_guard(s3_config_id) as (backend, uploaded_keys):
        file = db.query(EncounterFile).get(file_id)
        if not file:
            raise ValueError(f"EncounterFile {file_id} not found")

        # Get encounter for path construction
        encounter = db.query(PatientEncounters).get(file.patient_encounter_id)

        # 1. Upload image to S3
        image_path = IMAGE_DIR / encounter.zip_folder_name / file.filename
        if image_path.exists():
            s3_key_image = f"encounter_files/{file.uuid}/{file.filename}"
            backend.save_file(image_path, s3_key_image)
            uploaded_keys.append(s3_key_image)
            file.s3_object_key = s3_key_image
        else:
            raise StorageError(f"Image file not found: {image_path}")

        # 2. Upload thumbnail if exists
        if file.thumbnail_filename:
            thumb_path = IMAGE_DIR / encounter.zip_folder_name / file.thumbnail_filename
            if thumb_path.exists():
                s3_key_thumb = f"encounter_files/{file.uuid}/thumbnails/{file.thumbnail_filename}"
                backend.save_file(thumb_path, s3_key_thumb)
                uploaded_keys.append(s3_key_thumb)
                file.s3_object_key_thumbnail = s3_key_thumb

        # 3. Update DB
        file.s3_config_id = s3_config_id

        logger.info(f"Successfully migrated EncounterFile {file_id} to S3 config {s3_config_id}")
        return True


def migrate_encounter_file_pdf_to_s3(file_id: int, s3_config_id: int) -> bool:
    """
    Migrate an EncounterFilePDF from local to S3.

    Args:
        file_id: EncounterFilePDF ID
        s3_config_id: S3 config ID to use

    Returns:
        True on success

    Raises:
        StorageError: If migration fails
    """
    from models import EncounterFilePDF, PatientEncounters
    from app import PDF_DIR

    with s3_migration_guard(s3_config_id) as (backend, uploaded_keys):
        file = db.query(EncounterFilePDF).get(file_id)
        if not file:
            raise ValueError(f"EncounterFilePDF {file_id} not found")

        # Get encounter for path construction
        encounter = db.query(PatientEncounters).get(file.patient_encounter_id)

        # Upload PDF to S3
        pdf_path = PDF_DIR / encounter.zip_folder_name / file.filename
        if pdf_path.exists():
            s3_key_pdf = f"encounter_pdfs/{file.uuid}/{file.filename}"
            backend.save_file(pdf_path, s3_key_pdf)
            uploaded_keys.append(s3_key_pdf)
            file.s3_object_key = s3_key_pdf
        else:
            raise StorageError(f"PDF file not found: {pdf_path}")

        # Update DB
        file.s3_config_id = s3_config_id

        logger.info(f"Successfully migrated EncounterFilePDF {file_id} to S3 config {s3_config_id}")
        return True


def bulk_migrate_to_s3(
    model_name: str,
    file_ids: List[int],
    s3_config_id: int,
    batch_size: int = 100
) -> Tuple[int, List[Tuple[int, str]]]:
    """
    Bulk migrate files to S3 with batching and progress tracking.

    Args:
        model_name: Model name ('DirectImageUpload', 'EncounterFile', 'EncounterFilePDF')
        file_ids: List of file IDs to migrate
        s3_config_id: S3 config ID to use
        batch_size: Number of files per batch

    Returns:
        Tuple of (success_count, failed_list)
        failed_list contains (file_id, error_message) tuples
    """
    migration_funcs = {
        'DirectImageUpload': migrate_direct_upload_to_s3,
        'EncounterFile': migrate_encounter_file_to_s3,
        'EncounterFilePDF': migrate_encounter_file_pdf_to_s3,
    }

    if model_name not in migration_funcs:
        raise ValueError(f"Unknown model: {model_name}")

    migrate_func = migration_funcs[model_name]

    total = len(file_ids)
    success = 0
    failed = []

    logger.info(f"Starting bulk migration of {total} {model_name} files to S3 config {s3_config_id}")

    for i in range(0, total, batch_size):
        batch = file_ids[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} files)")

        for file_id in batch:
            try:
                migrate_func(file_id, s3_config_id)
                success += 1

                if success % 10 == 0:
                    logger.info(f"Progress: {success}/{total} files migrated")

            except Exception as e:
                failed.append((file_id, str(e)))
                logger.error(f"Failed to migrate {model_name} {file_id}: {e}")

        # Clear session periodically to prevent memory bloat
        db.session.expire_all()

    logger.info(f"Migration complete: {success}/{total} succeeded, {len(failed)} failed")

    if failed:
        logger.error(f"Failed migrations: {failed[:10]}")  # Log first 10 failures

    return success, failed


def migrate_all_local_files_to_s3(s3_config_id: int, dry_run: bool = False) -> dict:
    """
    Migrate all local files to S3.

    Args:
        s3_config_id: S3 config ID to use
        dry_run: If True, only count files without migrating

    Returns:
        Dictionary with migration statistics
    """
    from models import DirectImageUpload, EncounterFile, EncounterFilePDF

    stats = {
        'DirectImageUpload': {'total': 0, 'success': 0, 'failed': 0},
        'EncounterFile': {'total': 0, 'success': 0, 'failed': 0},
        'EncounterFilePDF': {'total': 0, 'success': 0, 'failed': 0},
    }

    # Get all files not yet in S3
    direct_uploads = db.query(DirectImageUpload).filter(
        DirectImageUpload.s3_config_id == None
    ).all()

    encounter_files = db.query(EncounterFile).filter(
        EncounterFile.s3_config_id == None
    ).all()

    encounter_pdfs = db.query(EncounterFilePDF).filter(
        EncounterFilePDF.s3_config_id == None
    ).all()

    stats['DirectImageUpload']['total'] = len(direct_uploads)
    stats['EncounterFile']['total'] = len(encounter_files)
    stats['EncounterFilePDF']['total'] = len(encounter_pdfs)

    if dry_run:
        logger.info(f"DRY RUN: Would migrate {stats}")
        return stats

    # Migrate DirectImageUploads
    if direct_uploads:
        ids = [u.id for u in direct_uploads]
        success, failed = bulk_migrate_to_s3('DirectImageUpload', ids, s3_config_id)
        stats['DirectImageUpload']['success'] = success
        stats['DirectImageUpload']['failed'] = len(failed)

    # Migrate EncounterFiles
    if encounter_files:
        ids = [f.id for f in encounter_files]
        success, failed = bulk_migrate_to_s3('EncounterFile', ids, s3_config_id)
        stats['EncounterFile']['success'] = success
        stats['EncounterFile']['failed'] = len(failed)

    # Migrate EncounterFilePDFs
    if encounter_pdfs:
        ids = [f.id for f in encounter_pdfs]
        success, failed = bulk_migrate_to_s3('EncounterFilePDF', ids, s3_config_id)
        stats['EncounterFilePDF']['success'] = success
        stats['EncounterFilePDF']['failed'] = len(failed)

    logger.info(f"Migration complete: {stats}")
    return stats
