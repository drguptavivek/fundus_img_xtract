# media/routes.py
"""
Media serving blueprint with S3 support and HMAC URL signing.

Supports both local file serving and S3 storage with:
- HMAC token validation for secure access
- Hospital isolation (cross-hospital access blocked)
- S3 presigned URL redirects (no proxy overhead)
- Local fallback when S3 unavailable
"""

import logging
from typing import NoReturn
from flask import request, redirect, abort
from flask_login import current_user, login_required
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
from authz.cache import get_hmac_validation, set_hmac_validation, token_digest
from authz.telemetry import record_authorization_decision
from media.authorization import (
    IMAGE_SOURCE_TYPES,
    MediaAccessDenied,
    MediaResolutionError,
    MediaSourceType,
    authorize_media_source,
    authorize_signed_media_source,
    resolve_media_source,
)

from . import bp

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("security.audit")


# ============================================================================
# HMAC-Signed Media Routes (New S3-aware routes)
# ============================================================================

@bp.route("/<uuid_str>", methods=["GET"])
@rate_limit("4000 per hour; 400 per minute", methods=["GET"], per_method=True)
def serve_media_with_hmac(uuid_str: str):
    return _serve_authorized_hmac(
        uuid_str,
        variant="original",
        expected_sources=IMAGE_SOURCE_TYPES | frozenset({MediaSourceType.ENCOUNTER_FILE_PDF}),
    )


@bp.route("/<uuid_str>/edited", methods=["GET"])
@rate_limit("2000 per hour; 100 per minute", methods=["GET"], per_method=True)
def serve_media_edited_with_hmac(uuid_str: str):
    return _serve_authorized_hmac(
        uuid_str,
        variant="edited",
        expected_sources=frozenset({MediaSourceType.DIRECT_IMAGE_UPLOAD}),
    )


@bp.route("/<uuid_str>/thumbnail", methods=["GET"])
@rate_limit_with_feedback("4000 per hour; 500 per minute", methods=["GET"], per_method=True)
def serve_media_thumbnail_with_hmac(uuid_str: str):
    return _serve_authorized_hmac(
        uuid_str,
        variant="thumbnail",
        expected_sources=IMAGE_SOURCE_TYPES,
    )


def _serve_authorized_hmac(uuid_str: str, *, variant: str, expected_sources):
    """Validate a signed credential, apply session auth when present, then deliver."""
    from utils.s3_storage_backends import generate_presigned_url, get_s3_client
    from utils.s3_url_signing import validate_media_token

    token = request.args.get("token")
    expires = request.args.get("expires")
    if not token or not expires:
        _reject_signed_media(400, "Invalid media URL")
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        _reject_signed_media(400, "Invalid media URL")

    with transaction_scope() as db:
        try:
            resource = resolve_media_source(db, media_uuid=uuid_str, expected_sources=expected_sources)
        except MediaResolutionError:
            _reject_signed_media(403, "Invalid or expired media token")
        if resource.hospital_id is None:
            _reject_signed_media(403, "Invalid or expired media token")
        digest = token_digest(token)
        valid = get_hmac_validation(
            token_hash=digest, media_uuid=uuid_str,
            hospital_id=resource.hospital_id, expires=expires_int,
        )
        if not valid:
            valid = validate_media_token(uuid_str, token, expires_int, resource.hospital_id)
            if valid:
                set_hmac_validation(
                    token_hash=digest, media_uuid=uuid_str,
                    hospital_id=resource.hospital_id, expires=expires_int,
                )
        if not valid:
            _reject_signed_media(403, "Invalid or expired media token")

        action = (
            "media.pdf.view"
            if resource.source_type == MediaSourceType.ENCOUNTER_FILE_PDF
            else "media.thumbnail.view" if variant == "thumbnail"
            else "media.image.view"
        )
        try:
            authorize_signed_media_source(resource=resource, action=action)
            if current_user.is_authenticated:
                authorize_media_source(
                    db, user=current_user, media_uuid=uuid_str,
                    action=action, expected_sources=expected_sources,
                )
        except (MediaAccessDenied, MediaResolutionError):
            abort(404)

        model_by_source = {
            MediaSourceType.DIRECT_IMAGE_UPLOAD: DirectImageUpload,
            MediaSourceType.ENCOUNTER_FILE: EncounterFile,
            MediaSourceType.ENCOUNTER_FILE_PDF: EncounterFilePDF,
        }
        row = db.get(model_by_source[resource.source_type], resource.source_id)
        if row is None:
            abort(404)
        if variant == "edited":
            object_key = getattr(row, "s3_object_key_edited", None)
        elif variant == "thumbnail":
            object_key = (
                getattr(row, "s3_object_key_edited_thumbnail", None)
                or getattr(row, "s3_object_key_thumbnail", None)
                or getattr(row, "s3_object_key_edited", None)
                or getattr(row, "s3_object_key", None)
            )
        else:
            object_key = getattr(row, "s3_object_key", None)
        s3_config_id = getattr(row, "s3_config_id", None)
        if s3_config_id and object_key:
            s3_config = db.get(S3Config, s3_config_id)
            if s3_config and s3_config.is_active:
                try:
                    kwargs = {"expires_in": 120} if variant == "thumbnail" else {}
                    url = generate_presigned_url(
                        get_s3_client(s3_config), s3_config, object_key, **kwargs
                    )
                    return redirect(url, code=307)
                except Exception as exc:
                    logger.warning(
                        "S3 media redirect failed uuid=%s error=%s",
                        sanitize_log_value(uuid_str), sanitize_log_value(exc),
                    )

        if resource.source_type == MediaSourceType.DIRECT_IMAGE_UPLOAD:
            if variant == "edited":
                return directImgEdByUUID(uuid_str, preauthorized=resource)
            if variant == "thumbnail":
                return directImgFinalThumbnailByUUID(uuid_str, preauthorized=resource)
            return directImgOrigByUUID(uuid_str, preauthorized=resource)
        if resource.source_type == MediaSourceType.ENCOUNTER_FILE:
            if variant == "thumbnail":
                return encounterImageThumbnailByUUID(uuid_str, preauthorized=resource)
            return encounterImageByUUID(uuid_str, preauthorized=resource)
        return encounterPDFByUUID(uuid_str, preauthorized=resource)


def _reject_signed_media(status_code: int, description: str) -> NoReturn:
    """Emit resource-blind credential telemetry, then stop signed delivery."""
    record_authorization_decision(
        action="media.signed.validate",
        allowed=False,
        actor_id=getattr(current_user, "id", None),
    )
    abort(status_code, description=description)


# ============================================================================
# Legacy routes authenticate at the transport boundary; object policy is
# enforced again inside the media layer.
# ============================================================================

@bp.route("/encounter/img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _encounterImageByUUID(uuid_str: str):
    return encounterImageByUUID(uuid_str)


@bp.route("/direct_upload/org_img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit("2000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgOrigByUUID(uuid_str: str):
    return directImgOrigByUUID(uuid_str)


@bp.route("/direct_upload/ed_img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit("2000 per hour; 100 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgEdByUUID(uuid_str: str):
    return directImgEdByUUID(uuid_str)


@bp.route("/direct_upload/fn_img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgFinalByUUID(uuid_str: str):
    return directImgFinalByUUID(uuid_str)


@bp.route("/img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit("1000 per hour; 300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _imgForGradingByUUID(uuid_str: str):
    return imgForGradingByUUID(uuid_str)


@bp.route("/encounter/pdf/<uuid_str>", methods=["GET"])
@login_required
@rate_limit("4000 per hour; 400 per minute", methods=["GET"], per_method=True, error_message="PDF fetch limit exceeded. Please slow down.")
def _encounterPDFByUUID(uuid_str: str):
    return encounterPDFByUUID(uuid_str)


# === Thumbnail Serving Routes ===

@bp.route("/encounter/img/<uuid_str>/thumbnail", methods=["GET"])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
@rate_limit("4000 per hour; 200 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _encounterSetImageByUUID(uuid_str: str):
    """Serve encounter set image by UUID."""
    return encounterSetImageByUUID(uuid_str)


@bp.route("/encounter_set/img/<uuid_str>/thumbnail", methods=["GET"])
@login_required
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
@login_required
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
