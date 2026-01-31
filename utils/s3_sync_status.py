"""
S3 Sync Status Tracking

Utilities for tracking S3 synchronization status of files.
Provides centralized tracking for upload/sync operations with retry support.
"""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session

from models import (
    S3SyncStatus, S3Config,
    EncounterFile, EncounterFilePDF, DirectImageUpload, EncounterSetImage
)
from db_transaction_manager import transaction_scope
from auth.utils import utcnow
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)

# File type constants
FileType = Literal["encounter_file", "encounter_file_pdf", "direct_upload", "encounter_set_image"]
SyncStatus = Literal["pending", "in_progress", "success", "failed"]
SyncVariant = Literal["original", "thumbnail", "edited", "edited_thumbnail"]


def create_sync_status(
    file_type: FileType,
    file_id: int,
    s3_config_id: int,
    variant: SyncVariant = "original",
    status: SyncStatus = "pending"
) -> S3SyncStatus:
    """
    Create a new sync status record.

    Args:
        file_type: Type of file (encounter_file, encounter_file_pdf, direct_upload, encounter_set_image)
        file_id: ID of the file record
        s3_config_id: S3 configuration ID
        variant: File variant (original, thumbnail, edited, edited_thumbnail)
        status: Initial status (default: pending)

    Returns:
        Created S3SyncStatus instance
    """
    with transaction_scope() as db:
        # Check if record already exists
        existing = db.execute(
            select(S3SyncStatus).where(
                and_(
                    S3SyncStatus.file_type == file_type,
                    S3SyncStatus.file_id == file_id,
                    S3SyncStatus.variant == variant
                )
            )
        ).scalar_one_or_none()

        if existing:
            logger.debug(
                "Sync status already exists for %s %s variant %s, updating status to %s",
                file_type, file_id, variant, status
            )
            existing.status = status
            existing.updated_at = utcnow()
            db.commit()
            db.refresh(existing)
            return existing

        sync_status = S3SyncStatus(
            file_type=file_type,
            file_id=file_id,
            s3_config_id=s3_config_id,
            variant=variant,
            status=status,
            attempt_count=0,
            created_at=utcnow(),
            updated_at=utcnow()
        )
        db.add(sync_status)
        db.commit()
        db.refresh(sync_status)

        logger.info(
            "Created sync status for %s %s variant %s: %s",
            file_type, file_id, variant, status
        )
        return sync_status


def update_sync_status(
    sync_id: int,
    status: SyncStatus,
    error_message: Optional[str] = None,
    mark_synced: bool = False
) -> bool:
    """
    Update sync status record.

    Args:
        sync_id: S3SyncStatus record ID
        status: New status
        error_message: Optional error message (for failed status)
        mark_synced: If True, set synced_at timestamp (for success status)

    Returns:
        True if updated, False if not found
    """
    with transaction_scope() as db:
        sync_status = db.execute(
            select(S3SyncStatus).where(S3SyncStatus.id == sync_id)
        ).scalar_one_or_none()

        if not sync_status:
            logger.warning("Sync status %d not found for update", sync_id)
            return False

        sync_status.status = status
        sync_status.updated_at = utcnow()

        if status == "in_progress":
            sync_status.attempt_count += 1
            sync_status.last_attempt_at = utcnow()
        elif status == "failed":
            sync_status.last_error = error_message
            sync_status.last_attempt_at = utcnow()
        elif status == "success" and mark_synced:
            sync_status.synced_at = utcnow()
            sync_status.last_error = None

        db.commit()

        logger.info(
            "Updated sync status %d to %s (attempts: %d)",
            sync_id, status, sync_status.attempt_count
        )
        return True


def get_sync_status(file_type: FileType, file_id: int) -> list[S3SyncStatus]:
    """
    Get all sync status records for a file.

    Args:
        file_type: Type of file
        file_id: ID of the file record

    Returns:
        List of S3SyncStatus records
    """
    with transaction_scope() as db:
        return list(db.execute(
            select(S3SyncStatus).where(
                and_(
                    S3SyncStatus.file_type == file_type,
                    S3SyncStatus.file_id == file_id
                )
            ).order_by(S3SyncStatus.variant)
        ).scalars().all())


def get_failed_syncs(s3_config_id: int, limit: int = 100) -> list[S3SyncStatus]:
    """
    Get failed sync statuses for an S3 config.

    Args:
        s3_config_id: S3 configuration ID
        limit: Maximum number of records to return

    Returns:
        List of failed S3SyncStatus records
    """
    with transaction_scope() as db:
        return list(db.execute(
            select(S3SyncStatus).where(
                and_(
                    S3SyncStatus.s3_config_id == s3_config_id,
                    S3SyncStatus.status == "failed"
                )
            ).order_by(
                S3SyncStatus.last_attempt_at.desc()
            ).limit(limit)
        ).scalars().all())


def get_sync_counts_by_hospital(hospital_id: int) -> dict:
    """
    Get sync status counts for a hospital.

    Returns:
        Dict with counts: {pending: int, success: int, failed: int, in_progress: int}
    """
    with transaction_scope() as db:
        # Get S3 config for hospital
        s3_config = db.execute(
            select(S3Config).where(
                and_(
                    S3Config.hospital_id == hospital_id,
                    S3Config.is_active == True
                )
            ).order_by(S3Config.id.desc())
        ).scalar_one_or_none()

        if not s3_config:
            return {"pending": 0, "success": 0, "failed": 0, "in_progress": 0, "has_s3": False}

        # Count by status
        counts = {}
        for status in ["pending", "success", "failed", "in_progress"]:
            count = db.execute(
                select(func.count(S3SyncStatus.id)).where(
                    and_(
                        S3SyncStatus.s3_config_id == s3_config.id,
                        S3SyncStatus.status == status
                    )
                )
            ).scalar() or 0
            counts[status] = count

        counts["has_s3"] = True
        counts["s3_config_id"] = s3_config.id

        return counts


def get_recent_sync_activity(s3_config_id: int, limit: int = 50) -> list[dict]:
    """
    Get recent sync activity for an S3 config.

    Returns:
        List of dicts with sync activity details
    """
    with transaction_scope() as db:
        syncs = db.execute(
            select(S3SyncStatus).where(
                S3SyncStatus.s3_config_id == s3_config_id
            ).order_by(
                S3SyncStatus.updated_at.desc()
            ).limit(limit)
        ).scalars().all()

        result = []
        for sync in syncs:
            result.append({
                "id": sync.id,
                "file_type": sync.file_type,
                "file_id": sync.file_id,
                "variant": sync.variant,
                "status": sync.status,
                "attempt_count": sync.attempt_count,
                "last_error": sync.last_error,
                "last_attempt_at": sync.last_attempt_at.isoformat() if sync.last_attempt_at else None,
                "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
                "created_at": sync.created_at.isoformat() if sync.created_at else None,
            })

        return result


def get_file_by_sync(sync_status: S3SyncStatus, db: Session):
    """
    Get the actual file record for a sync status.

    Args:
        sync_status: S3SyncStatus instance
        db: Database session

    Returns:
        The file record (EncounterFile, DirectImageUpload, etc.) or None
    """
    file_models = {
        "encounter_file": EncounterFile,
        "encounter_file_pdf": EncounterFilePDF,
        "direct_upload": DirectImageUpload,
        "encounter_set_image": EncounterSetImage,
    }

    model = file_models.get(sync_status.file_type)
    if not model:
        return None

    return db.execute(
        select(model).where(model.id == sync_status.file_id)
    ).scalar_one_or_none()


def mark_sync_pending(
    file_type: FileType,
    file_id: int,
    s3_config_id: int,
    variant: SyncVariant = "original"
) -> S3SyncStatus:
    """
    Mark a file as pending sync (creates or updates status).

    This is the entry point for tracking new files that need to be synced.
    """
    return create_sync_status(file_type, file_id, s3_config_id, variant, "pending")


def mark_sync_in_progress(sync_id: int) -> bool:
    """Mark a sync as in progress (increments attempt count)."""
    return update_sync_status(sync_id, "in_progress")


def mark_sync_success(sync_id: int) -> bool:
    """Mark a sync as successful."""
    return update_sync_status(sync_id, "success", mark_synced=True)


def mark_sync_failed(sync_id: int, error_message: str) -> bool:
    """Mark a sync as failed with error message."""
    return update_sync_status(sync_id, "failed", error_message=error_message)
