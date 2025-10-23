# media/routes.py
from auth.roles import roles_required
from utils.rate_limiter import rate_limit
from utils.utilsImgServe import (
    directImgFinalByUUID,
    directImgOrigByUUID,
    encounterImageByUUID,
    directImgEdByUUID,
    imgForGradingByUUID,
    encounterPDFByUUID,
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
