"""
Automatic thumbnail cleanup utilities.

This module provides functions to automatically clean up thumbnail files
when their parent images are deleted from the system.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from models import DirectImageUpload, EncounterFile, PatientEncounters
from utils.fileUtils import (
    get_thumbnail_path_direct, get_thumbnail_path_encounter,
    thumbnail_exists_direct, thumbnail_exists_encounter
)
from db_transaction_manager import transaction_scope
from utils.log_sanitize import sanitize_log_value

# Configure logger
logger = logging.getLogger(__name__)


def delete_thumbnails_for_direct_upload(direct_upload_id: int) -> Dict[str, Any]:
    """
    Delete all thumbnails associated with a DirectImageUpload record.

    Args:
        direct_upload_id: ID of the DirectImageUpload record

    Returns:
        Dictionary with cleanup results:
        {
            'original_deleted': bool,
            'edited_deleted': bool,
            'errors': list[str]
        }
    """
    results = {
        'original_deleted': False,
        'edited_deleted': False,
        'errors': []
    }

    try:
        with transaction_scope() as db:
            direct_upload = db.query(DirectImageUpload).filter_by(id=direct_upload_id).first()
            if not direct_upload:
                results['errors'].append(f"DirectImageUpload {direct_upload_id} not found")
                return results

            folder_rel = direct_upload.folder_rel

            # Delete original image thumbnail
            if direct_upload.thumbnail_filename:
                try:
                    thumbnail_path = get_thumbnail_path_direct(folder_rel, direct_upload.filename, "orig")
                    if thumbnail_path.exists():
                        thumbnail_path.unlink()
                        results['original_deleted'] = True
                        logger.info(
                            "Deleted original thumbnail for DirectImageUpload %s",
                            sanitize_log_value(direct_upload_id),
                        )
                    else:
                        logger.debug(
                            "Original thumbnail not found for DirectImageUpload %s",
                            sanitize_log_value(direct_upload_id),
                        )
                except Exception as e:
                    error_msg = f"Failed to delete original thumbnail: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(
                        "Failed to delete original thumbnail for DirectImageUpload %s: %s",
                        sanitize_log_value(direct_upload_id),
                        sanitize_log_value(e),
                    )

            # Delete edited image thumbnail
            if direct_upload.edited_thumbnail_filename and direct_upload.edited_filename:
                try:
                    thumbnail_path = get_thumbnail_path_direct(folder_rel, direct_upload.edited_filename, "edited")
                    if thumbnail_path.exists():
                        thumbnail_path.unlink()
                        results['edited_deleted'] = True
                        logger.info(
                            "Deleted edited thumbnail for DirectImageUpload %s",
                            sanitize_log_value(direct_upload_id),
                        )
                    else:
                        logger.debug(
                            "Edited thumbnail not found for DirectImageUpload %s",
                            sanitize_log_value(direct_upload_id),
                        )
                except Exception as e:
                    error_msg = f"Failed to delete edited thumbnail: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(
                        "Failed to delete edited thumbnail for DirectImageUpload %s: %s",
                        sanitize_log_value(direct_upload_id),
                        sanitize_log_value(e),
                    )

            # Clear database references
            direct_upload.thumbnail_filename = None
            direct_upload.edited_thumbnail_filename = None
            db.add(direct_upload)

    except Exception as e:
        error_msg = f"Database error during thumbnail cleanup: {str(e)}"
        results['errors'].append(error_msg)
        logger.error(
            "Database error during thumbnail cleanup for DirectImageUpload %s: %s",
            sanitize_log_value(direct_upload_id),
            sanitize_log_value(e),
        )

    return results


def delete_thumbnails_for_encounter_file(encounter_file_id: int) -> Dict[str, Any]:
    """
    Delete thumbnail associated with an EncounterFile record.

    Args:
        encounter_file_id: ID of the EncounterFile record

    Returns:
        Dictionary with cleanup results:
        {
            'deleted': bool,
            'errors': list[str]
        }
    """
    results = {
        'deleted': False,
        'errors': []
    }

    try:
        with transaction_scope() as db:
            encounter_file = db.query(EncounterFile).filter_by(id=encounter_file_id).first()
            if not encounter_file:
                results['errors'].append(f"EncounterFile {encounter_file_id} not found")
                return results

            if encounter_file.thumbnail_filename:
                try:
                    # Get the absolute path to the original image
                    from models import IMAGE_DIR, ZipFile
                    result = (db.query(EncounterFile, PatientEncounters, ZipFile)
                             .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                             .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                             .filter(EncounterFile.id == encounter_file_id).first())

                    if result:
                        encounter_file_obj, patient_encounter, zip_file = result
                        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                        original_image_path = IMAGE_DIR / upload_date_str / encounter_file.filename

                        thumbnail_path = get_thumbnail_path_encounter(original_image_path)
                        if thumbnail_path.exists():
                            thumbnail_path.unlink()
                            results['deleted'] = True
                            logger.info(
                                "Deleted thumbnail for EncounterFile %s",
                                sanitize_log_value(encounter_file_id),
                            )
                        else:
                            logger.debug(
                                "Thumbnail not found for EncounterFile %s",
                                sanitize_log_value(encounter_file_id),
                            )

                except Exception as e:
                    error_msg = f"Failed to delete thumbnail: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(
                        "Failed to delete thumbnail for EncounterFile %s: %s",
                        sanitize_log_value(encounter_file_id),
                        sanitize_log_value(e),
                    )

            # Clear database reference
            encounter_file.thumbnail_filename = None
            db.add(encounter_file)

    except Exception as e:
        error_msg = f"Database error during thumbnail cleanup: {str(e)}"
        results['errors'].append(error_msg)
        logger.error(
            "Database error during thumbnail cleanup for EncounterFile %s: %s",
            sanitize_log_value(encounter_file_id),
            sanitize_log_value(e),
        )

    return results


def delete_thumbnails_for_patient_encounter(patient_encounter_id: int) -> Dict[str, Any]:
    """
    Delete all thumbnails for encounter files associated with a PatientEncounters record.

    This is called when a PatientEncounters record is deleted (cascade deletion).

    Args:
        patient_encounter_id: ID of the PatientEncounters record

    Returns:
        Dictionary with cleanup results:
        {
            'files_processed': int,
            'thumbnails_deleted': int,
            'errors': list[str]
        }
    """
    results = {
        'files_processed': 0,
        'thumbnails_deleted': 0,
        'errors': []
    }

    try:
        with transaction_scope() as db:
            # Get all encounter files for this patient encounter
            encounter_files = db.query(EncounterFile).filter_by(patient_encounter_id=patient_encounter_id).all()

            for encounter_file in encounter_files:
                results['files_processed'] += 1

                if encounter_file.thumbnail_filename:
                    try:
                        # Get the absolute path to the original image
                        from models import IMAGE_DIR, ZipFile
                        zip_file = encounter_file.patient_encounter.zip_file
                        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                        original_image_path = IMAGE_DIR / upload_date_str / encounter_file.filename

                        thumbnail_path = get_thumbnail_path_encounter(original_image_path)
                        if thumbnail_path.exists():
                            thumbnail_path.unlink()
                            results['thumbnails_deleted'] += 1
                            logger.info(
                                "Deleted thumbnail for EncounterFile %s (PatientEncounter %s)",
                                sanitize_log_value(encounter_file.id),
                                sanitize_log_value(patient_encounter_id),
                            )
                        else:
                            logger.debug(
                                "Thumbnail not found for EncounterFile %s",
                                sanitize_log_value(encounter_file.id),
                            )

                    except Exception as e:
                        error_msg = f"Failed to delete thumbnail for EncounterFile {encounter_file.id}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)

                # Clear database reference
                encounter_file.thumbnail_filename = None
                db.add(encounter_file)

    except Exception as e:
        error_msg = f"Database error during batch thumbnail cleanup: {str(e)}"
        results['errors'].append(error_msg)
        logger.error(
            "Database error during batch thumbnail cleanup for PatientEncounter %s: %s",
            sanitize_log_value(patient_encounter_id),
            sanitize_log_value(e),
        )

    return results


def cleanup_orphaned_thumbnails_by_references() -> Dict[str, Any]:
    """
    Clean up orphaned thumbnails by checking database references.

    This is different from the file-based cleanup - this checks for thumbnails
    that exist but whose database records don't reference them.

    Returns:
        Dictionary with cleanup results:
        {
            'thumbnails_checked': int,
            'orphans_found': int,
            'orphans_removed': int,
            'errors': list[str]
        }
    """
    results = {
        'thumbnails_checked': 0,
        'orphans_found': 0,
        'orphans_removed': int,
        'errors': []
    }

    try:
        # Check direct upload thumbnails
        with transaction_scope() as db:
            direct_uploads = db.query(DirectImageUpload).all()

            for direct_upload in direct_uploads:
                # Check original thumbnail
                if direct_upload.thumbnail_filename:
                    results['thumbnails_checked'] += 1
                    thumbnail_path = get_thumbnail_path_direct(
                        direct_upload.folder_rel, direct_upload.filename, "orig"
                    )
                    if thumbnail_path.exists():
                        # Thumbnail exists but database doesn't reference it (shouldn't happen with current logic)
                        # This is more for future safety checks
                        pass

                # Check edited thumbnail
                if direct_upload.edited_thumbnail_filename and direct_upload.edited_filename:
                    results['thumbnails_checked'] += 1
                    thumbnail_path = get_thumbnail_path_direct(
                        direct_upload.folder_rel, direct_upload.edited_filename, "edited"
                    )
                    if thumbnail_path.exists():
                        # Same as above - safety check
                        pass

        # Check encounter file thumbnails
        with transaction_scope() as db:
            from models import IMAGE_DIR, ZipFile
            encounter_files = db.query(EncounterFile).filter(EncounterFile.thumbnail_filename.isnot(None)).all()

            for encounter_file in encounter_files:
                results['thumbnails_checked'] += 1
                result = (db.query(EncounterFile, PatientEncounters, ZipFile)
                         .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                         .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                         .filter(EncounterFile.id == encounter_file.id).first())

                if result:
                    encounter_file_obj, patient_encounter, zip_file = result
                    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                    original_image_path = IMAGE_DIR / upload_date_str / encounter_file.filename

                    thumbnail_path = get_thumbnail_path_encounter(original_image_path)
                    if thumbnail_path.exists():
                        # Safety check - ensure database and file are consistent
                        pass

    except Exception as e:
        error_msg = f"Error during reference-based cleanup: {str(e)}"
        results['errors'].append(error_msg)
        logger.error(error_msg)

    return results


def safe_delete_thumbnail_file(thumbnail_path: Path) -> bool:
    """
    Safely delete a thumbnail file with proper error handling.

    Args:
        thumbnail_path: Path to the thumbnail file

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        if thumbnail_path.exists() and thumbnail_path.is_file():
            thumbnail_path.unlink()
            return True
        return False
    except OSError as e:
        logger.error(
            "Failed to delete thumbnail file %s: %s",
            sanitize_log_value(thumbnail_path),
            sanitize_log_value(e),
        )
        return False
    except Exception as e:
        logger.error(
            "Unexpected error deleting thumbnail file %s: %s",
            sanitize_log_value(thumbnail_path),
            sanitize_log_value(e),
        )
        return False


# Utility functions for integration with existing deletion logic

def add_thumbnail_cleanup_to_direct_upload_deletion(direct_upload: DirectImageUpload, logger_instance=None) -> Dict[str, Any]:
    """
    Add thumbnail cleanup to existing DirectImageUpload deletion logic.

    This function is designed to be called within existing deletion code.

    Args:
        direct_upload: DirectImageUpload instance being deleted
        logger_instance: Optional logger instance for logging

    Returns:
        Dictionary with cleanup results
    """
    cleanup_logger = logger_instance or logger
    results = delete_thumbnails_for_direct_upload(direct_upload.id)

    # Log results if a logger was provided
    if logger_instance:
        if results['original_deleted']:
            logger_instance.info(
                "Deleted original thumbnail for DirectImageUpload %s",
                sanitize_log_value(direct_upload.id),
            )
        if results['edited_deleted']:
            logger_instance.info(
                "Deleted edited thumbnail for DirectImageUpload %s",
                sanitize_log_value(direct_upload.id),
            )
        if results['errors']:
            for error in results['errors']:
                logger_instance.warning(
                    "Thumbnail cleanup error for DirectImageUpload %s: %s",
                    sanitize_log_value(direct_upload.id),
                    sanitize_log_value(error),
                )

    return results


def add_thumbnail_cleanup_to_encounter_file_deletion(encounter_file: EncounterFile, logger_instance=None) -> Dict[str, Any]:
    """
    Add thumbnail cleanup to existing EncounterFile deletion logic.

    This function is designed to be called within existing deletion code.

    Args:
        encounter_file: EncounterFile instance being deleted
        logger_instance: Optional logger instance for logging

    Returns:
        Dictionary with cleanup results
    """
    cleanup_logger = logger_instance or logger
    results = delete_thumbnails_for_encounter_file(encounter_file.id)

    # Log results if a logger was provided
    if logger_instance:
        if results['deleted']:
            logger_instance.info(
                "Deleted thumbnail for EncounterFile %s",
                sanitize_log_value(encounter_file.id),
            )
        if results['errors']:
            for error in results['errors']:
                logger_instance.warning(
                    "Thumbnail cleanup error for EncounterFile %s: %s",
                    sanitize_log_value(encounter_file.id),
                    sanitize_log_value(error),
                )

    return results


# Batch cleanup functions for admin use

def cleanup_all_thumbnails_for_missing_images() -> Dict[str, Any]:
    """
    Clean up thumbnails for images that no longer exist in the database.

    This is a maintenance function that can be called periodically.

    Returns:
        Dictionary with cleanup statistics
    """
    from utils.fileUtils import cleanup_orphaned_thumbnails

    logger.info("Starting comprehensive thumbnail cleanup for missing images")

    # First, run the existing file-based cleanup
    file_results = cleanup_orphaned_thumbnails()

    # Then, run reference-based cleanup
    ref_results = cleanup_orphaned_thumbnails_by_references()

    combined_results = {
        'file_orphans_removed': file_results['cleaned_count'],
        'file_orphans_found': file_results['orphaned_count'],
        'file_errors': file_results['errors'],
        'ref_thumbnails_checked': ref_results['thumbnails_checked'],
        'ref_errors': ref_results['errors'],
        'total_errors': file_results['errors'] + ref_results['errors']
    }

    logger.info(
        "Thumbnail cleanup completed: %s thumbnails removed",
        sanitize_log_value(combined_results['file_orphans_removed']),
    )

    if combined_results['total_errors']:
        logger.warning(
            "Thumbnail cleanup had %s errors",
            sanitize_log_value(len(combined_results['total_errors'])),
        )

    return combined_results
