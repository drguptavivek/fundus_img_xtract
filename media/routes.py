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

from flask import abort, request
from flask_login import current_user, login_required

from db_transaction_manager import transaction_scope
from media.delivery import deliver_media
from media.authorization import (
    IMAGE_SOURCE_TYPES,
    MediaAccessDenied,
    MediaResolutionError,
    MediaSourceType,
    authorize_media_source,
    authorize_signed_media_source,
    resolve_media_source,
)
from models import (
    DirectImageUpload,
    EncounterFile,
)
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import rate_limit, rate_limit_with_feedback
from utils.utilsImgServe import (
    directImgEdByUUID,
    directImgEdThumbnailByUUID,
    directImgFinalByUUID,
    directImgFinalThumbnailByUUID,
    directImgOrigByUUID,
    directImgOrigThumbnailByUUID,
    encounterImageByUUID,
    # Thumbnail serving functions
    encounterImageThumbnailByUUID,
    encounterPDFByUUID,
    encounterSetImageByUUID,
    encounterSetImageEditedByUUID,
    encounterSetImageThumbnailByUUID,
    imgForGradingByUUID,
    universalImageThumbnailByUUID,
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
        expected_sources=IMAGE_SOURCE_TYPES
        | frozenset({MediaSourceType.ENCOUNTER_FILE_PDF}),
    )


@bp.route("/<uuid_str>/edited", methods=["GET"])
@rate_limit("2000 per hour; 100 per minute", methods=["GET"], per_method=True)
def serve_media_edited_with_hmac(uuid_str: str):
    return _serve_authorized_hmac(
        uuid_str,
        variant="edited",
        expected_sources=frozenset(
            {
                MediaSourceType.DIRECT_IMAGE_UPLOAD,
                MediaSourceType.ENCOUNTER_SET_IMAGE,
            }
        ),
    )


@bp.route("/<uuid_str>/thumbnail", methods=["GET"])
@rate_limit_with_feedback(
    "4000 per hour; 500 per minute", methods=["GET"], per_method=True
)
def serve_media_thumbnail_with_hmac(uuid_str: str):
    return _serve_authorized_hmac(
        uuid_str,
        variant="thumbnail",
        expected_sources=IMAGE_SOURCE_TYPES,
    )


def _serve_authorized_hmac(uuid_str: str, *, variant: str, expected_sources):
    """Validate a signed credential, apply session auth when present, then deliver."""
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
            resource = resolve_media_source(
                db, media_uuid=uuid_str, expected_sources=expected_sources
            )
        except MediaResolutionError:
            _reject_signed_media(403, "Invalid or expired media token")
        if resource.hospital_id is None:
            _reject_signed_media(403, "Invalid or expired media token")
        valid = validate_media_token(
            uuid_str, token, expires_int, resource.hospital_id
        )
        if not valid:
            _reject_signed_media(403, "Invalid or expired media token")

        try:
            authorize_signed_media_source(resource=resource)
        except (MediaAccessDenied, MediaResolutionError):
            abort(404)

        return deliver_media(db, resource, variant=variant)


def _reject_signed_media(status_code: int, description: str) -> NoReturn:
    """Stop signed delivery without revealing whether the resource exists."""
    abort(status_code, description=description)


# ============================================================================
# Legacy routes authenticate at the transport boundary; object policy is
# enforced again inside the media layer.
# ============================================================================


@bp.route("/encounter/img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit(
    "4000 per hour; 200 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
def _encounterImageByUUID(uuid_str: str):
    return encounterImageByUUID(uuid_str)


@bp.route("/direct_upload/org_img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit(
    "2000 per hour; 200 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
def _directImgOrigByUUID(uuid_str: str):
    return directImgOrigByUUID(uuid_str)


@bp.route("/direct_upload/ed_img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit(
    "2000 per hour; 100 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
def _directImgEdByUUID(uuid_str: str):
    return directImgEdByUUID(uuid_str)


@bp.route("/direct_upload/fn_img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit(
    "4000 per hour; 200 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
def _directImgFinalByUUID(uuid_str: str):
    return directImgFinalByUUID(uuid_str)


@bp.route("/img/<uuid_str>", methods=["GET"])
@login_required
@rate_limit(
    "1000 per hour; 300 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
def _imgForGradingByUUID(uuid_str: str):
    return imgForGradingByUUID(uuid_str)


@bp.route("/encounter/pdf/<uuid_str>", methods=["GET"])
@login_required
@rate_limit(
    "4000 per hour; 400 per minute",
    methods=["GET"],
    per_method=True,
    error_message="PDF fetch limit exceeded. Please slow down.",
)
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
@rate_limit(
    "4000 per hour; 200 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
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
@rate_limit(
    "4000 per hour; 200 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Image fetch limit exceeded. Please slow down.",
)
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
