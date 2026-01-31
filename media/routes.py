# media/routes.py
"""
Media serving blueprint with S3 support and HMAC URL signing.

Supports both local file serving and S3 storage with:
- HMAC token validation for secure access
- Hospital isolation (cross-hospital access blocked)
- S3 presigned URL redirects (no proxy overhead)
- Local fallback when S3 unavailable
"""

import os
from flask import request, redirect, abort, current_app
from auth.roles import roles_required
from utils.rate_limiter import rate_limit, rate_limit_with_feedback
from utils.utilsImgServe import (
    directImgFinalByUUID,
    directImgOrigByUUID,
    encounterImageByUUID,
    directImgEdByUUID,
    imgForGradingByUUID,
    encounterPDFByUUID,
    # Thumbnail serving functions
    encounterImageThumbnailByUUID,
    directImgOrigThumbnailByUUID,
    directImgEdThumbnailByUUID,
    directImgFinalThumbnailByUUID,
    universalImageThumbnailByUUID,
    encounterSetImageByUUID,
    encounterSetImageThumbnailByUUID,
    encounterSetImageEditedByUUID,
)
from utils.log_sanitize import sanitize_log_value
from db_transaction_manager import transaction_scope
from models import DirectImageUpload, EncounterFile, EncounterFilePDF, S3Config

from . import bp

logger = current_app.logger if current_app else None
audit_logger = current_app.audit_logger if current_app else None


# ============================================================================
# HMAC-Signed Media Routes (New S3-aware routes)
# ============================================================================

@bp.route("/<uuid_str>", methods=["GET"])
def serve_media_with_hmac(uuid_str: str):
    """
    Serve media file using HMAC-signed URL.

    URL Format: /media/{uuid}?token={hmac}&expires={timestamp}

    Security Flow:
    1. Validate HMAC token (hospital-specific pepper)
    2. Check hospital access (user's hospital = file's hospital)
    3. Check if file has S3 metadata
    4. If S3: Generate presigned URL and redirect
    5. If not S3: Serve from local filesystem

    This route provides:
    - Hospital isolation (HMAC validation)
    - Cross-hospital access blocking
    - Direct S3 redirects (performance)
    - Local fallback (compatibility)
    """
    from flask_login import current_user
    from utils.s3_url_signing import validate_media_token
    from utils.s3_storage_backends import get_s3_client, generate_presigned_url

    # Get token and expires from query parameters
    token = request.args.get('token')
    expires = request.args.get('expires')

    if not token or not expires:
        # Missing HMAC parameters - return 400 (not 403 to avoid information leak)
        logger.warning("Media request missing HMAC parameters for uuid=%s", sanitize_log_value(uuid_str))
        abort(400, description="Invalid media URL")

    try:
        expires_int = int(expires)
    except (ValueError, TypeError):
        logger.warning("Media request has invalid expires parameter for uuid=%s", sanitize_log_value(uuid_str))
        abort(400, description="Invalid media URL")

    # Get file metadata and validate HMAC
    with transaction_scope() as db:
        # Try to find file in DirectImageUpload first
        file_record = db.query(DirectImageUpload).filter_by(uuid=uuid_str).first()

        if not file_record:
            # Try EncounterFile
            file_record = db.query(EncounterFile).filter_by(uuid=uuid_str).first()

        if not file_record:
            # Try EncounterFilePDF
            file_record = db.query(EncounterFilePDF).filter_by(uuid=uuid_str).first()

        if not file_record:
            logger.warning("Media file not found for uuid=%s", sanitize_log_value(uuid_str))
            abort(404, description="File not found")

        # Get hospital_id from file record
        hospital_id = getattr(file_record, 'hospital_id', None)

        if not hospital_id:
            logger.warning("File has no hospital_id for uuid=%s", sanitize_log_value(uuid_str))
            abort(403, description="Access denied")

        # Validate HMAC token with hospital-specific pepper
        if not validate_media_token(uuid_str, token, expires_int, hospital_id):
            audit_logger.warning(
                "MEDIA_HMAC_VALIDATION_FAILED | uuid=%s | hospital_id=%s | token=%s | expires=%s",
                sanitize_log_value(uuid_str),
                hospital_id,
                sanitize_log_value(token[:16] + "..."),
                expires_int
            )
            abort(403, description="Invalid or expired media token")

        # Check if user has access to this hospital
        if current_user and current_user.is_authenticated:
            user_hospitals = [u.id for u in current_user.lab_units] if current_user.lab_units else []
            if hospital_id not in user_hospitals:
                audit_logger.warning(
                    "MEDIA_CROSS_HOSPITAL_BLOCKED | uuid=%s | file_hospital=%s | user_hospitals=%s",
                    sanitize_log_value(uuid_str),
                    hospital_id,
                    user_hospitals
                )
                abort(403, description="Cross-hospital access blocked")

        # Check if file has S3 metadata
        s3_config_id = getattr(file_record, 's3_config_id', None)
        s3_object_key = getattr(file_record, 's3_object_key', None)

        if s3_config_id and s3_object_key:
            # File is stored in S3 - generate presigned URL and redirect
            s3_config = db.query(S3Config).get(s3_config_id)

            if not s3_config or not s3_config.is_active:
                logger.warning(
                    "S3 config not active for s3_config_id=%d, falling back to local",
                    s3_config_id
                )
            else:
                try:
                    # Get S3 client
                    s3_client = get_s3_client(s3_config)

                    # Get file size for TTL calculation (optional)
                    file_size = getattr(file_record, 'file_size', None)

                    # Generate presigned URL
                    presigned_url = generate_presigned_url(
                        s3_client,
                        s3_config,
                        s3_object_key,
                        file_size_bytes=file_size
                    )

                    audit_logger.info(
                        "MEDIA_S3_REDIRECT | uuid=%s | s3_config_id=%d | hospital_id=%d | object_key=%s",
                        sanitize_log_value(uuid_str),
                        s3_config_id,
                        hospital_id,
                        sanitize_log_value(s3_object_key)
                    )

                    # Redirect to S3 (client downloads directly from S3)
                    return redirect(presigned_url, code=307)

                except Exception as e:
                    logger.error(
                        "Failed to generate S3 presigned URL for uuid=%s, s3_config_id=%d: %s",
                        sanitize_log_value(uuid_str),
                        s3_config_id,
                        e
                    )
                    # Local-first: fall back to local serving on S3 failure
                    logger.info("S3 presigned URL generation failed, serving from local (local-first policy)")

        # No S3 metadata or S3 failed with fallback="always"
        # Serve from local filesystem
        if isinstance(file_record, DirectImageUpload):
            return _serve_direct_local(file_record, uuid_str)
        elif isinstance(file_record, EncounterFile):
            return _serve_encounter_local(file_record, uuid_str)
        elif isinstance(file_record, EncounterFilePDF):
            return encounterPDFByUUID(uuid_str)

        abort(404, description="File not found")


@bp.route("/<uuid_str>/edited", methods=["GET"])
def serve_media_edited_with_hmac(uuid_str: str):
    """
    Serve edited media file using HMAC-signed URL.

    URL Format: /media/{uuid}/edited?token={hmac}&expires={timestamp}

    Only works for DirectImageUpload with edited versions.
    """
    from flask_login import current_user
    from utils.s3_url_signing import validate_media_token
    from utils.s3_storage_backends import get_s3_client, generate_presigned_url

    token = request.args.get('token')
    expires = request.args.get('expires')

    if not token or not expires:
        abort(400, description="Invalid media URL")

    try:
        expires_int = int(expires)
    except (ValueError, TypeError):
        abort(400, description="Invalid media URL")

    with transaction_scope() as db:
        file_record = db.query(DirectImageUpload).filter_by(uuid=uuid_str).first()

        if not file_record or not file_record.edited_filename:
            abort(404, description="Edited file not found")

        hospital_id = file_record.hospital_id
        if not hospital_id:
            abort(403, description="Access denied")

        # Validate HMAC token
        if not validate_media_token(uuid_str, token, expires_int, hospital_id):
            abort(403, description="Invalid or expired media token")

        # Check hospital access
        if current_user and current_user.is_authenticated:
            user_hospitals = [u.id for u in current_user.lab_units] if current_user.lab_units else []
            if hospital_id not in user_hospitals:
                abort(403, description="Cross-hospital access blocked")

        # Check for S3 metadata
        s3_config_id = file_record.s3_config_id
        s3_object_key = file_record.s3_object_key_edited

        if s3_config_id and s3_object_key:
            s3_config = db.query(S3Config).get(s3_config_id)

            if s3_config and s3_config.is_active:
                try:
                    s3_client = get_s3_client(s3_config)
                    presigned_url = generate_presigned_url(
                        s3_client,
                        s3_config,
                        s3_object_key
                    )
                    return redirect(presigned_url, code=307)
                except Exception as e:
                    logger.error("Failed to generate S3 presigned URL for edited file: %s", e)
                    # Local-first: fall back to local serving on S3 failure
                    logger.info("S3 presigned URL generation failed for edited file, serving from local (local-first policy)")

        # Fallback to local
        return directImgEdByUUID(uuid_str)


@bp.route("/<uuid_str>/thumbnail", methods=["GET"])
def serve_media_thumbnail_with_hmac(uuid_str: str):
    """
    Serve thumbnail using HMAC-signed URL.

    URL Format: /media/{uuid}/thumbnail?token={hmac}&expires={timestamp}
    """
    from flask_login import current_user
    from utils.s3_url_signing import validate_media_token
    from utils.s3_storage_backends import get_s3_client, generate_presigned_url

    token = request.args.get('token')
    expires = request.args.get('expires')

    if not token or not expires:
        abort(400, description="Invalid media URL")

    try:
        expires_int = int(expires)
    except (ValueError, TypeError):
        abort(400, description="Invalid media URL")

    with transaction_scope() as db:
        # Try DirectImageUpload first
        file_record = db.query(DirectImageUpload).filter_by(uuid=uuid_str).first()

        if not file_record:
            # Try EncounterFile
            file_record = db.query(EncounterFile).filter_by(uuid=uuid_str).first()

        if not file_record:
            abort(404, description="File not found")

        hospital_id = getattr(file_record, 'hospital_id', None)
        if not hospital_id:
            abort(403, description="Access denied")

        # Validate HMAC token
        if not validate_media_token(uuid_str, token, expires_int, hospital_id):
            abort(403, description="Invalid or expired media token")

        # Check hospital access
        if current_user and current_user.is_authenticated:
            user_hospitals = [u.id for u in current_user.lab_units] if current_user.lab_units else []
            if hospital_id not in user_hospitals:
                abort(403, description="Cross-hospital access blocked")

        # Check for S3 thumbnail metadata
        s3_config_id = getattr(file_record, 's3_config_id', None)

        # Use appropriate thumbnail key based on file type
        if isinstance(file_record, DirectImageUpload):
            s3_object_key = file_record.s3_object_key_edited_thumbnail or file_record.s3_object_key_thumbnail
            if not s3_object_key and file_record.edited_filename:
                s3_object_key = file_record.s3_object_key_edited
            elif not s3_object_key:
                s3_object_key = file_record.s3_object_key
        else:
            s3_object_key = getattr(file_record, 's3_object_key_thumbnail', None)

        if s3_config_id and s3_object_key:
            s3_config = db.query(S3Config).get(s3_config_id)

            if s3_config and s3_config.is_active:
                try:
                    s3_client = get_s3_client(s3_config)
                    presigned_url = generate_presigned_url(
                        s3_client,
                        s3_config,
                        s3_object_key,
                        expires_in=120  # Shorter TTL for thumbnails
                    )
                    return redirect(presigned_url, code=307)
                except Exception as e:
                    logger.error("Failed to generate S3 presigned URL for thumbnail: %s", e)
                    # Local-first: fall back to local serving on S3 failure
                    logger.info("S3 presigned URL generation failed for thumbnail, serving from local (local-first policy)")

        # Fallback to local thumbnail serving
        if isinstance(file_record, DirectImageUpload):
            return directImgFinalThumbnailByUUID(uuid_str)
        else:
            return encounterImageThumbnailByUUID(uuid_str)


# ============================================================================
# Legacy Routes (RBAC-protected, kept for compatibility)
# ============================================================================

@bp.route("/encounter/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _encounterImageByUUID(uuid_str: str):
    return encounterImageByUUID(uuid_str)


@bp.route("/direct_upload/org_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("2000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgOrigByUUID(uuid_str: str):
    return directImgOrigByUUID(uuid_str)


@bp.route("/direct_upload/ed_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("2000 per hour; 100 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgEdByUUID(uuid_str: str):
    return directImgEdByUUID(uuid_str)


@bp.route("/direct_upload/fn_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgFinalByUUID(uuid_str: str):
    return directImgFinalByUUID(uuid_str)


@bp.route("/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("1000 per hour; 300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _imgForGradingByUUID(uuid_str: str):
    return imgForGradingByUUID(uuid_str)


@bp.route("/encounter/pdf/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("4000 per hour; 400 per minute", methods=["GET"], per_method=True, error_message="PDF fetch limit exceeded. Please slow down.")
def _encounterPDFByUUID(uuid_str: str):
    return encounterPDFByUUID(uuid_str)


# === Thumbnail Serving Routes ===

@bp.route("/encounter/img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _encounterImageThumbnailByUUID(uuid_str: str):
    """Serve thumbnail for encounter (ZIP upload) images."""
    return encounterImageThumbnailByUUID(uuid_str)


@bp.route("/direct_upload/org_img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _directImgOrigThumbnailByUUID(uuid_str: str):
    """Serve thumbnail for direct upload original images."""
    return directImgOrigThumbnailByUUID(uuid_str)


@bp.route("/direct_upload/ed_img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _directImgEdThumbnailByUUID(uuid_str: str):
    """Serve thumbnail for direct upload edited images."""
    return directImgEdThumbnailByUUID(uuid_str)


@bp.route("/direct_upload/fn_img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _directImgFinalThumbnailByUUID(uuid_str: str):
    """Serve thumbnail for direct upload images (prefers edited, falls back to original)."""
    return directImgFinalThumbnailByUUID(uuid_str)


@bp.route("/img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _universalImageThumbnailByUUID(uuid_str: str):
    """Universal thumbnail serving that works for both encounter and direct upload images."""
    return universalImageThumbnailByUUID(uuid_str)


# === Encounter Set Media Routes ===

@bp.route("/encounter_set/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _encounterSetImageByUUID(uuid_str: str):
    """Serve encounter set image by UUID."""
    return encounterSetImageByUUID(uuid_str)


@bp.route("/encounter_set/img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _encounterSetImageThumbnailByUUID(uuid_str: str):
    """Serve encounter set thumbnail by UUID."""
    return encounterSetImageThumbnailByUUID(uuid_str)


@bp.route("/encounter_set/img/<uuid_str>/edited", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _encounterSetImageEditedByUUID(uuid_str: str):
    """Serve encounter set edited image by UUID (only if edited version exists)."""
    return encounterSetImageEditedByUUID(uuid_str)


# ============================================================================
# Local Fallback Helpers
# ============================================================================

def _serve_direct_local(direct_image: DirectImageUpload, uuid: str):
    """Serve DirectImageUpload from local filesystem."""
    # Prefer edited image, fallback to original
    if direct_image.edited_filename:
        return directImgEdByUUID(uuid)
    return directImgOrigByUUID(uuid)


def _serve_encounter_local(encounter_file: EncounterFile, uuid: str):
    """Serve EncounterFile from local filesystem."""
    return encounterImageByUUID(uuid)
