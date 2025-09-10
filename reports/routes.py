# reports/routes.py
from flask import abort, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
from auth.roles import roles_required

from . import bp

# Reuse the same locations you configured for split PDFs
# (these were moved to .env in your earlier steps)
from models import DR_PDF_DIR, GLAUCOMA_PDF_DIR, Session, DiabeticRetinopathyReport, GlaucomaReport, PatientEncounters, ZipFile
from utils.utilsImgServe import encounterDrReportByUUID, encounterGlaucomaReportByUUID

# --- Serve split report PDFs by report UUIDs ---
@bp.route("/dr/by-uuid/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_dr_pdf_by_uuid(uuid: str):
    return encounterDrReportByUUID(uuid)


@bp.route("/glaucoma/by-uuid/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_glaucoma_pdf_by_uuid(uuid: str):
    return encounterGlaucomaReportByUUID(uuid)


@bp.route("/glaucoma_results", methods=["GET"])
@roles_required("admin")
def glaucoma_results_redirect():
    # Redirect old path to new blueprint path
    return redirect(url_for("verify_remedio_glaucoma.glaucoma_results"), code=302)
 
