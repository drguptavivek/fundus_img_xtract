# reports/routes.py
from flask import abort, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
from auth.roles import roles_required

from . import bp

# Reuse the same locations you configured for split PDFs
# (these were moved to .env in your earlier steps)
from models import DR_PDF_DIR, GLAUCOMA_PDF_DIR, Session, DiabeticRetinopathyReport, GlaucomaReport, PatientEncounters, ZipFile

# --- Serve split report PDFs by report UUIDs ---
@bp.route("/dr/by-uuid/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_dr_pdf_by_uuid(uuid: str):
    db = Session()
    try:
        # Join with PatientEncounters and ZipFile to get the upload date
        rep = (
            db.query(DiabeticRetinopathyReport, PatientEncounters, ZipFile)
            .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(DiabeticRetinopathyReport.uuid == uuid)
            .first()
        )
    finally:
        db.close()

    if not rep or not rep[0].report_file_name:
        abort(404)
        
    # Extract the report, patient encounter, and zip file objects
    report, patient_encounter, zip_file = rep
    
    # Get the upload date and format it as YYYY_MM_DD
    upload_date = zip_file.upload_date
    upload_date_str = upload_date.strftime("%Y_%m_%d") if upload_date else ""
    
    # Construct the path to the dated subdirectory
    dated_dir = DR_PDF_DIR / upload_date_str
    
    directory, fname = _safe_file(dated_dir, report.report_file_name)
    return send_from_directory(directory=directory, path=fname, mimetype="application/pdf", as_attachment=False)


@bp.route("/glaucoma/by-uuid/<uuid>", methods=["GET"])
@roles_required("admin")
def serve_glaucoma_pdf_by_uuid(uuid: str):
    db = Session()
    try:
        # Join with PatientEncounters and ZipFile to get the upload date
        rep = (
            db.query(GlaucomaReport, PatientEncounters, ZipFile)
            .join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(GlaucomaReport.uuid == uuid)
            .first()
        )
    finally:
        db.close()

    if not rep or not rep[0].report_file_name:
        abort(404)
        
    # Extract the report, patient encounter, and zip file objects
    report, patient_encounter, zip_file = rep
    
    # Get the upload date and format it as YYYY_MM_DD
    upload_date = zip_file.upload_date
    upload_date_str = upload_date.strftime("%Y_%m_%d") if upload_date else ""
    
    # Construct the path to the dated subdirectory
    dated_dir = GLAUCOMA_PDF_DIR / upload_date_str
    
    directory, fname = _safe_file(dated_dir, report.report_file_name)
    return send_from_directory(directory=directory, path=fname, mimetype="application/pdf", as_attachment=False)


@bp.route("/glaucoma_results", methods=["GET"])
@roles_required("admin")
def glaucoma_results_redirect():
    # Redirect old path to new blueprint path
    return redirect(url_for("verify_remedio_glaucoma.glaucoma_results"), code=302)
 
