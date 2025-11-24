# media/routes.py
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
)

from . import bp

@bp.route("/encounter/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _encounterImageByUUID(uuid_str: str):
    return encounterImageByUUID(uuid_str)

@bp.route("/direct_upload/org_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgOrigByUUID(uuid_str: str):
    return directImgOrigByUUID(uuid_str)


@bp.route("/direct_upload/ed_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgEdByUUID(uuid_str: str):
    return directImgEdByUUID(uuid_str)

@bp.route("/direct_upload/fn_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _directImgFinalByUUID(uuid_str: str):
    return directImgFinalByUUID(uuid_str)

@bp.route("/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("300 per minute", methods=["GET"], per_method=True, error_message="Image fetch limit exceeded. Please slow down.")
def _imgForGradingByUUID(uuid_str: str):
    return imgForGradingByUUID(uuid_str)

@bp.route("/encounter/pdf/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit("200 per minute", methods=["GET"], per_method=True, error_message="PDF fetch limit exceeded. Please slow down.")
def _encounterPDFByUUID(uuid_str: str):
    return encounterPDFByUUID(uuid_str)

# === Thumbnail Serving Routes ===

@bp.route("/encounter/img/<uuid_str>/thumbnail", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
@rate_limit_with_feedback(
    "5000 per hour; 900 per minute",
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
    "5000 per hour; 900 per minute",
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
    "5000 per hour; 900 per minute",
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
    "5000 per hour; 900 per minute",
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
    "5000 per hour; 900 per minute",
    methods=["GET"],
    per_method=True,
    error_message="Thumbnail fetch limit exceeded. Please slow down.",
)
def _universalImageThumbnailByUUID(uuid_str: str):
    """Universal thumbnail serving that works for both encounter and direct upload images."""
    return universalImageThumbnailByUUID(uuid_str)
