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

logger = logging.getLogger(__name__)


def trigger_direct_upload_thumbnails(direct_upload_id: int, user_context: Optional[Dict[str, Any]] = None):
    """
    Trigger thumbnail generation for a direct upload image.

    This function should be called after a direct upload is completed.

    Args:
        direct_upload_id: ID of the DirectImageUpload record
        user_context: Optional user context (will use current_user if not provided)
    """
    try:
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
        schedule_direct_upload_thumbnails(direct_upload_id, current_app, user_context)
        logger.info(f"Triggered thumbnails for direct upload {direct_upload_id}")

    except Exception as e:
        logger.error(f"Failed to trigger thumbnails for direct upload {direct_upload_id}: {str(e)}")


def trigger_encounter_thumbnails(encounter_file_ids, user_context: Optional[Dict[str, Any]] = None):
    """
    Trigger thumbnail generation for encounter files (ZIP uploads).

    This function should be called after ZIP processing is completed.

    Args:
        encounter_file_ids: List or single ID of EncounterFile records
        user_context: Optional user context (will use current_user if not provided)
    """
    try:
        # Convert single ID to list
        if isinstance(encounter_file_ids, int):
            encounter_file_ids = [encounter_file_ids]

        if not encounter_file_ids:
            return

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
        schedule_encounter_thumbnails(encounter_file_ids, current_app, user_context)
        logger.info(f"Triggered thumbnails for {len(encounter_file_ids)} encounter files")

    except Exception as e:
        logger.error(f"Failed to trigger thumbnails for encounter files: {str(e)}")


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
                logger.info(f"Created batch thumbnail job for direct uploads: {job_token}")

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
                logger.info(f"Created batch thumbnail job for encounter files: {job_token}")

        total_processed = len(direct_references) + len(encounter_references)
        logger.info(f"Triggered batch thumbnails for {total_processed} existing images")

    except Exception as e:
        logger.error(f"Failed to trigger batch thumbnails: {str(e)}")


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
                logger.error(f"Failed to trigger thumbnails in decorator: {str(e)}")
                # Don't raise the error to avoid breaking the main function

            return result
        return wrapper
    return decorator


# Flask blueprint helper
def setup_thumbnail_routes(bp):
    """
    Add thumbnail-related routes to a Flask blueprint.

    Args:
        bp: Flask blueprint to add routes to
    """
    from flask import jsonify, request
    from flask_login import login_required, current_user
    from auth.roles import roles_required
    from utils.thumbnail_jobs import get_thumbnail_job_status
    from utils.fileUtils import cleanup_orphaned_thumbnails

    @bp.route('/api/thumbnails/job/<job_token>/status')
    @login_required
    def get_job_status(job_token):
        """Get status of a thumbnail generation job."""
        status = get_thumbnail_job_status(job_token)
        if not status:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(status)

    @bp.route('/api/thumbnails/cleanup', methods=['POST'])
    @roles_required('admin', 'data_manager')
    def cleanup_thumbnails():
        """Clean up orphaned thumbnails."""
        stats = cleanup_orphaned_thumbnails()
        return jsonify({
            'orphaned_count': stats['orphaned_count'],
            'cleaned_count': stats['cleaned_count'],
            'errors': stats['errors']
        })

    @bp.route('/api/thumbnails/batch', methods=['POST'])
    @roles_required('admin', 'data_manager')
    def batch_thumbnails():
        """Trigger batch thumbnail generation for existing images."""
        data = request.get_json() or {}
        limit = min(int(data.get('limit', 100)), 1000)  # Cap at 1000
        lab_unit_id = data.get('lab_unit_id')

        trigger_batch_existing_thumbnails(limit, lab_unit_id)
        return jsonify({
            'message': f'Batch thumbnail generation triggered for up to {limit} images'
        })