"""
S3 Upload Handler for Multi-Tenant File Storage

Provides utilities for uploading files to S3 with hospital-scoped configurations.
Supports fallback to local filesystem when S3 is unavailable (based on policy).

Usage:
    >>> from utils.s3_upload_handler import upload_file_to_s3, get_active_s3_config
    >>> s3_config = get_active_s3_config(hospital_id=1)
    >>> if s3_config:
    ...     object_key = upload_file_to_s3(s3_config, file_content, "uploads/img.jpg")
    ...     # Store object_key in database
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Literal
from werkzeug.datastructures import FileStorage

from db_transaction_manager import get_db_session
from models import S3Config
from utils.s3_storage_backends import get_s3_client
from utils.log_sanitize import sanitize_log_value
from utils.s3_validation import validate_s3_object_key, sanitize_for_s3_key

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('security.audit')


# Upload result types
UploadResult = tuple[Literal["s3", "local"], str | None]  # (backend, object_key_or_path)


def get_active_s3_config(hospital_id: int) -> S3Config | None:
    """
    Get active S3 configuration for a hospital.

    Args:
        hospital_id: Hospital ID to get config for

    Returns:
        S3Config instance if active config exists, None otherwise
    """
    with get_db_session() as db:
        s3_config = db.query(S3Config).filter_by(
            hospital_id=hospital_id,
            is_active=True
        ).first()
        return s3_config


def generate_s3_object_key(
    hospital_id: int,
    file_type: str,  # "original", "edited", "thumbnail", "edited_thumbnail"
    filename: str,
    date_str: str = None
) -> str:
    """
    Generate S3 object key for a file.

    Key format: {hospital_id}/{file_type}/{YYYY_MM_DD}/{filename}

    Args:
        hospital_id: Hospital ID
        file_type: Type of file (original, edited, thumbnail, edited_thumbnail)
        filename: Original filename
        date_str: Optional date string (defaults to today)

    Returns:
        S3 object key

    Example:
        >>> generate_s3_object_key(1, "original", "image.jpg", "2025_01_25")
        "1/original/2025_01_25/image.jpg"
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")

    # Sanitize filename for S3
    safe_filename = Path(filename).name  # Get basename only
    # Remove any non-ASCII characters for safety
    safe_filename = safe_filename.encode('ascii', 'ignore').decode('ascii').strip()
    if not safe_filename:
        safe_filename = "file"

    return f"{hospital_id}/{file_type}/{date_str}/{safe_filename}"


def calculate_file_hash(file_content: bytes | BinaryIO) -> str:
    """
    Calculate SHA-256 hash of file content.

    Args:
        file_content: File content as bytes or file-like object

    Returns:
        Hex-encoded SHA-256 hash
    """
    if isinstance(file_content, bytes):
        return hashlib.sha256(file_content).hexdigest()
    else:
        # File-like object
        pos = file_content.tell()
        file_content.seek(0)
        content = file_content.read()
        file_content.seek(pos)  # Reset position
        return hashlib.sha256(content).hexdigest()


def upload_file_to_s3(
    s3_config: S3Config,
    file_content: bytes | BinaryIO,
    object_key: str,
    content_type: str = None
) -> str:
    """
    Upload file to S3 using hospital's configuration.

    Args:
        s3_config: S3Config instance for the hospital
        file_content: File content as bytes or file-like object
        object_key: S3 object key (path within bucket)
        content_type: Optional content-type header

    Returns:
        The S3 ETag of the uploaded object

    Raises:
        ValueError: If upload fails
    """
    try:
        # Get S3 client
        s3_client = get_s3_client(s3_config)

        # Build full key with path prefix
        full_key = object_key
        if s3_config.path_prefix:
            full_key = f"{s3_config.path_prefix.rstrip('/')}/{object_key}"

        # Prepare upload parameters
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type

        # Reset position if file-like object
        if isinstance(file_content, bytes):
            content_bytes = file_content
        else:
            pos = file_content.tell()
            file_content.seek(0)
            content_bytes = file_content.read()
            file_content.seek(pos)

        # Upload to S3
        response = s3_client.put_object(
            Bucket=s3_config.bucket_name,
            Key=full_key,
            Body=content_bytes,
            **extra_args
        )

        audit_logger.info(
            "S3_FILE_UPLOADED | s3_config_id=%d | hospital_id=%d | object_key=%s | "
            "bucket=%s | etag=%s",
            s3_config.id,
            s3_config.hospital_id,
            sanitize_log_value(object_key),
            sanitize_log_value(s3_config.bucket_name),
            sanitize_log_value(response.get('ETag', ''))
        )

        return response.get('ETag', '')

    except Exception as e:
        logger.error(
            "Failed to upload to S3 for hospital_id=%d, object_key=%s: %s",
            s3_config.hospital_id,
            sanitize_log_value(object_key),
            e
        )
        raise ValueError(f"S3 upload failed: {e}")


def upload_with_fallback(
    file_content: bytes | BinaryIO,
    filename: str,
    hospital_id: int,
    file_type: str = "original",
    local_save_func = None,
    content_type: str = None
) -> UploadResult:
    """
    Upload file to S3 with fallback to local filesystem.

    Upload strategy:
    1. If hospital has active S3 config, upload to S3
    2. If S3 upload fails and fallback_policy="always", save to local
    3. If no S3 config, save to local

    Args:
        file_content: File content as bytes or file-like object
        filename: Original filename
        hospital_id: Hospital ID
        file_type: Type of file (original, edited, thumbnail, edited_thumbnail)
        local_save_func: Optional function to save to local filesystem
        content_type: Optional content-type header

    Returns:
        (backend, location) tuple where:
        - backend: "s3" or "local"
        - location: S3 object key or local file path

    Example:
        >>> backend, location = upload_with_fallback(
        ...     file_content, "image.jpg", hospital_id=1
        ... )
        >>> if backend == "s3":
        ...     s3_object_key = location
        ... else:
        ...     local_path = location
    """
    s3_config = get_active_s3_config(hospital_id)
    local_path = None

    # Try S3 upload if config exists
    if s3_config:
        try:
            object_key = generate_s3_object_key(hospital_id, file_type, filename)
            etag = upload_file_to_s3(s3_config, file_content, object_key, content_type)

            logger.info(
                "S3 upload successful for hospital_id=%d, file_type=%s, filename=%s, object_key=%s",
                hospital_id,
                file_type,
                sanitize_log_value(filename),
                sanitize_log_value(object_key)
            )

            return ("s3", object_key)

        except Exception as e:
            logger.warning(
                "S3 upload failed for hospital_id=%d, file=%s: %s",
                hospital_id,
                sanitize_log_value(filename),
                e
            )

            # Check fallback policy
            if s3_config.fallback_policy == "never":
                # Fail hard - don't save locally
                audit_logger.error(
                    "S3_UPLOAD_FAILED_NO_FALLBACK | hospital_id=%d | filename=%s | "
                    "fallback_policy=never | error=%s",
                    hospital_id,
                    sanitize_log_value(filename),
                    sanitize_log_value(str(e))
                )
                raise ValueError(f"S3 upload failed and fallback policy is 'never': {e}")

            # Fallback to local storage
            logger.info(
                "Falling back to local storage for hospital_id=%d, filename=%s",
                hospital_id,
                sanitize_log_value(filename)
            )

    # No S3 config or fallback enabled - save to local filesystem
    if local_save_func:
        local_path = local_save_func(file_content, filename)
        return ("local", local_path)
    else:
        # No local save function provided
        raise ValueError("S3 not available and no local fallback function provided")


def delete_from_s3(
    s3_config: S3Config,
    object_key: str
) -> bool:
    """
    Delete file from S3.

    Args:
        s3_config: S3Config instance
        object_key: S3 object key to delete

    Returns:
        True if deleted, False if object not found
    """
    try:
        s3_client = get_s3_client(s3_config)

        # Build full key with path prefix
        full_key = object_key
        if s3_config.path_prefix:
            full_key = f"{s3_config.path_prefix.rstrip('/')}/{object_key}"

        s3_client.delete_object(
            Bucket=s3_config.bucket_name,
            Key=full_key
        )

        audit_logger.info(
            "S3_FILE_DELETED | s3_config_id=%d | hospital_id=%d | object_key=%s",
            s3_config.id,
            s3_config.hospital_id,
            sanitize_log_value(object_key)
        )

        return True

    except s3_client.exceptions.NoSuchKey:
        logger.warning(
            "S3 object not found for deletion (already deleted?): hospital_id=%d, object_key=%s",
            s3_config.hospital_id,
            sanitize_log_value(object_key)
        )
        return False

    except Exception as e:
        logger.error(
            "Failed to delete from S3 for hospital_id=%d, object_key=%s: %s",
            s3_config.hospital_id,
            sanitize_log_value(object_key),
            e
        )
        return False


def generate_media_url_with_token(
    file_uuid: str,
    hospital_id: int,
    variant: str = "orig"
) -> str | None:
    """
    Generate HMAC-signed media URL for a file.

    Convenience wrapper for utils.s3_url_signing.generate_media_url.

    Args:
        file_uuid: File UUID
        hospital_id: Hospital ID
        variant: "orig" or "edited"

    Returns:
        Complete media URL with token and expires parameters, or None if no S3 config

    Example:
        >>> url = generate_media_url_with_token("abc-123", hospital_id=1)
        >>> "/media/abc-123?token=7a8f3b...&expires=1735200000"
    """
    try:
        from utils.s3_url_signing import generate_media_url
        return generate_media_url(file_uuid, hospital_id, variant=variant)
    except Exception as e:
        logger.warning(
            "Failed to generate media URL for uuid=%s, hospital_id=%s: %s",
            file_uuid,
            hospital_id,
            e
        )
        return None


def get_storage_backend_info(hospital_id: int) -> dict | None:
    """
    Get storage backend information for a hospital.

    Returns:
        Dict with backend info or None if no S3 config:
        - backend: "s3" or "local"
        - provider: S3 provider (if S3)
        - bucket_name: S3 bucket (if S3)
    """
    s3_config = get_active_s3_config(hospital_id)
    if s3_config:
        return {
            "backend": "s3",
            "provider": s3_config.provider,
            "bucket_name": s3_config.bucket_name,
            "s3_config_id": s3_config.id,
            "fallback_policy": s3_config.fallback_policy,
        }
    else:
        return {
            "backend": "local",
        }


# ============================================================================
# FileStorage Adapter for Direct Upload Integration
# ============================================================================

class S3FileStorageAdapter:
    """
    Adapter class for saving files to S3.

    Designed to work with existing upload code by providing
    a file-like interface that handles S3 uploads.
    """

    def __init__(self, hospital_id: int, file_type: str = "original"):
        """
        Initialize adapter for a hospital and file type.

        Args:
            hospital_id: Hospital ID
            file_type: Type of file (original, edited, thumbnail, etc.)
        """
        self.hospital_id = hospital_id
        self.file_type = file_type
        self.s3_config = get_active_s3_config(hospital_id)
        self.s3_object_key = None
        self.backend = "local"

    @property
    def has_s3_config(self) -> bool:
        """Check if hospital has active S3 configuration."""
        return self.s3_config is not None

    def save(self, file_content: bytes | BinaryIO, filename: str) -> tuple[str, str]:
        """
        Save file to S3 (or fallback to local).

        Args:
            file_content: File content
            filename: Original filename

        Returns:
            (backend, location) tuple where:
            - backend: "s3" or "local"
            - location: S3 object key or local file path

        Raises:
            ValueError: If no S3 config and no local save function
        """
        if self.s3_config:
            try:
                object_key = generate_s3_object_key(
                    self.hospital_id,
                    self.file_type,
                    filename
                )
                upload_file_to_s3(self.s3_config, file_content, object_key)
                self.s3_object_key = object_key
                self.backend = "s3"
                return ("s3", object_key)
            except Exception as e:
                if self.s3_config.fallback_policy == "never":
                    raise ValueError(f"S3 upload failed and fallback is disabled: {e}")
                logger.warning("S3 upload failed, will use local storage: %s", e)

        # Fallback to local
        self.backend = "local"
        return ("local", None)

    def delete(self, object_key: str) -> bool:
        """Delete file from S3 if stored there."""
        if self.s3_config and object_key:
            return delete_from_s3(self.s3_config, object_key)
        return False
