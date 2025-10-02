"""Routes for serving reports-related assets and redirects."""

from flask import redirect, url_for

from auth.roles import roles_required

from . import bp
from utils.utilsImgServe import encounterDrReportByUUID, encounterGlaucomaReportByUUID


@bp.route("/dr/by-uuid/<uuid>", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def serve_dr_pdf_by_uuid(uuid: str):
    return encounterDrReportByUUID(uuid)


@bp.route("/glaucoma/by-uuid/<uuid>", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def serve_glaucoma_pdf_by_uuid(uuid: str):
    return encounterGlaucomaReportByUUID(uuid)


@bp.route("/glaucoma_results", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def glaucoma_results_redirect():
    return redirect(url_for("verify_remedio_glaucoma.glaucoma_results"), code=302)
