# media/routes.py
from auth.roles import roles_required
from utils.utilsImgServe import (directImgFinalByUUID, 
    directImgOrigByUUID, encounterImageByUUID, directImgEdByUUID,imgForGradingByUUID)

from . import bp

@bp.route("/encounter/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
def _encounterImageByUUID(uuid_str: str):
    return encounterImageByUUID(uuid_str)

@bp.route("/direct_upload/org_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
def _directImgOrigByUUID(uuid_str: str):
    return directImgOrigByUUID(uuid_str)


@bp.route("/direct_upload/ed_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
def _directImgEdByUUID(uuid_str: str):
    return directImgEdByUUID(uuid_str)

@bp.route("/direct_upload/fn_img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
def _directImgFinalByUUID(uuid_str: str):
    return directImgFinalByUUID(uuid_str)

@bp.route("/img/<uuid_str>", methods=["GET"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin", "ophthalmologist", "resident")
def _imgForGradingByUUID(uuid_str: str):
    return imgForGradingByUUID(uuid_str)
