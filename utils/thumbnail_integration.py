"""
Thumbnail integration helpers for easy integration with existing upload workflows.

This module provides simple functions to trigger thumbnail generation
after image uploads, edits, or processing.
"""

import logging
from typing import Optional, Dict, Any
from flask import current_app
from flask_login import current_user

from utils.thumbnail_jobs import (
    schedule_direct_upload_thumbnails,
    schedule_encounter_thumbnails,
    create_user_context
)
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)


def trigger_direct_upload_thumbnails(direct_upload_id: int, app=None, user_context: Optional[Dict[str, Any]] = None):
    """
    Trigger thumbnail generation for a direct upload image.

    This function should be called after a direct upload is completed.

    Args:
        direct_upload_id: ID of the DirectImageUpload record
        app: Flask application instance (will use current_app if not provided)
        user_context: Optional user context (will use current_user if not provided)
    """
    try:
        # Use provided app or current_app (if in request context)
        if app is None:
            app = current_app

        # Create user context if not provided
        if user_context is None and current_user.is_authenticated:
            from flask import request
            user_context = create_user_context(
                user_id=current_user.id,
                username=current_user.username,
                ip=request.remote_addr
            )
        elif user_context is None:
            # Default context for system-triggered jobs
            user_context = create_user_context(
                user_id=None,
                username='system',
                ip='127.0.0.1'
            )

        # Schedule thumbnail generation
        schedule_direct_upload_thumbnails(direct_upload_id, app, user_context)
        logger.info(
            "Triggered thumbnails for direct upload %s",
            sanitize_log_value(direct_upload_id),
        )

    except Exception as e:
        logger.error(
            "Failed to trigger thumbnails for direct upload %s: %s",
            sanitize_log_value(direct_upload_id),
            sanitize_log_value(e),
        )


def trigger_encounter_thumbnails(encounter_file_ids, app=None, user_context: Optional[Dict[str, Any]] = None):
    """
    Trigger thumbnail generation for encounter files (ZIP uploads).

    This function should be called after ZIP processing is completed.

    Args:
        encounter_file_ids: List or single ID of EncounterFile records
        app: Flask application instance (will use current_app if not provided)
        user_context: Optional user context (will use current_user if not provided)
    """
    try:
        # Convert single ID to list
        if isinstance(encounter_file_ids, int):
            encounter_file_ids = [encounter_file_ids]

        if not encounter_file_ids:
            return

        # Use provided app or current_app (if in request context)
        if app is None:
            app = current_app

        # Create user context if not provided
        if user_context is None and current_user.is_authenticated:
            from flask import request
            user_context = create_user_context(
                user_id=current_user.id,
                username=current_user.username,
                ip=request.remote_addr
            )
        elif user_context is None:
            # Default context for system-triggered jobs
            user_context = create_user_context(
                user_id=None,
                username='system',
                ip='127.0.0.1'
            )

        # Schedule thumbnail generation
        schedule_encounter_thumbnails(encounter_file_ids, app, user_context)
        logger.info(
            "Triggered thumbnails for %s encounter files",
            sanitize_log_value(len(encounter_file_ids)),
        )

    except Exception as e:
        logger.error(
            "Failed to trigger thumbnails for encounter files: %s",
            sanitize_log_value(e),
        )


def trigger_batch_existing_thumbnails(limit: int = 100, lab_unit_id: Optional[int] = None):
    """
    Trigger thumbnail generation for existing images that don't have thumbnails.

    This is an admin function for generating thumbnails for existing images.

    Args:
        limit: Maximum number of images to process
        lab_unit_id: Optional lab unit filter
    """
    try:
        from models import DirectImageUpload, EncounterFile
        from db_transaction_manager import transaction_scope
        from utils.thumbnail_jobs import ThumbnailJobType, create_thumbnail_job, queue_thumbnail_job

        user_context = create_user_context(
            user_id=None,
            username='batch_system',
            ip='127.0.0.1'
        )

        # Find direct uploads without thumbnails
        direct_references = []
        with transaction_scope() as db:
            query = db.query(DirectImageUpload).filter(
                DirectImageUpload.thumbnail_filename.is_(None)
            )

            if lab_unit_id:
                query = query.filter(DirectImageUpload.lab_unit_id == lab_unit_id)

            direct_uploads = query.limit(limit // 2).all()

            for du in direct_uploads:
                direct_references.append({
                    'image_id': du.id,
                    'folder_rel': du.folder_rel,
                    'filename': du.filename
                })

        # Find encounter files without thumbnails
        encounter_references = []
        with transaction_scope() as db:
            query = db.query(EncounterFile).filter(
                EncounterFile.thumbnail_filename.is_(None)
            )

            encounter_files = query.limit(limit // 2).all()

            for ef in encounter_files:
                encounter_references.append({
                    'image_id': ef.id,
                })

        # Create jobs for both types
        if direct_references:
            job_token = create_thumbnail_job(
                ThumbnailJobType.DIRECT_ORIGINAL,
                direct_references,
                uploader_user_id=None,
                uploader_username='batch_system',
                uploader_ip='127.0.0.1',
                lab_unit_id=lab_unit_id
            )
            if job_token:
                queue_thumbnail_job(job_token, current_app)
                logger.info(
                    "Created batch thumbnail job for direct uploads: %s",
                    sanitize_log_value(job_token),
                )

        if encounter_references:
            job_token = create_thumbnail_job(
                ThumbnailJobType.ENCOUNTER,
                encounter_references,
                uploader_user_id=None,
                uploader_username='batch_system',
                uploader_ip='127.0.0.1',
                lab_unit_id=lab_unit_id
            )
            if job_token:
                queue_thumbnail_job(job_token, current_app)
                logger.info(
                    "Created batch thumbnail job for encounter files: %s",
                    sanitize_log_value(job_token),
                )

        total_processed = len(direct_references) + len(encounter_references)
        logger.info(
            "Triggered batch thumbnails for %s existing images",
            sanitize_log_value(total_processed),
        )

    except Exception as e:
        logger.error(
            "Failed to trigger batch thumbnails: %s",
            sanitize_log_value(e),
        )


# Decorator for automatic thumbnail triggering
def with_thumbnails(image_type: str = 'direct'):
    """
    Decorator to automatically trigger thumbnails after a function completes.

    Args:
        image_type: 'direct' for DirectImageUpload, 'encounter' for EncounterFile

    Usage:
        @with_thumbnails('direct')
        def upload_direct_image(data):
            # ... upload logic ...
            return direct_upload_id
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            try:
                if image_type == 'direct' and isinstance(result, int):
                    # Assume result is DirectImageUpload ID
                    trigger_direct_upload_thumbnails(result)
                elif image_type == 'encounter':
                    # Handle both single ID and list of IDs
                    if isinstance(result, int):
                        trigger_encounter_thumbnails([result])
                    elif isinstance(result, list) and all(isinstance(x, int) for x in result):
                        trigger_encounter_thumbnails(result)
            except Exception as e:
                logger.error(
                    "Failed to trigger thumbnails in decorator: %s",
                    sanitize_log_value(e),
                )
                # Don't raise the error to avoid breaking the main function

            return result
        return wrapper
    return decorator
