import os
from pathlib import Path
from flask import send_file, abort, flash
from models import Session, EncounterFile, PatientEncounters, ZipFile, IMAGE_DIR, DiabeticRetinopathyReport, GlaucomaReport, PDF_DIR, DirectImageUpload, BASE_DIR, DR_PDF_DIR, GLAUCOMA_PDF_DIR, DIRECT_UPLOAD_DIR

def encounterImageByUUID(uuid: str):
    db = Session()
    try:
        result = (db.query(EncounterFile, PatientEncounters, ZipFile).join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id).join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id).filter(EncounterFile.uuid == uuid).first())
        if not result or not result[0].filename: 
            flash(f"Error: Encounter image not found with UUID: {uuid}", "danger")
            abort(404)
        encounter_file, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        image_path_str = str(IMAGE_DIR / upload_date_str / encounter_file.filename)
        if not os.path.exists(image_path_str): 
            flash(f"Error: Image file not found on disk: {uuid}", "danger")
            abort(404)
        file_extension = Path(encounter_file.filename).suffix.lower()
        mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
        mimetype = mimetype_map.get(file_extension, 'image/jpeg')
        return send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}")
    finally: db.close()

def encounterDrReportByUUID(uuid: str):
    db = Session()
    try:
        result = (db.query(DiabeticRetinopathyReport, PatientEncounters, ZipFile).join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id).join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id).filter(DiabeticRetinopathyReport.uuid == uuid).first())
        if not result or not result[0].report_file_name: 
            abort(404)
        dr_report, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(DR_PDF_DIR / upload_date_str / dr_report.report_file_name)
        if not os.path.exists(pdf_path_str): 
            flash(f"Error: DR report not found with UUID: {uuid}", "danger")
            abort(404)
        return send_file(pdf_path_str, mimetype='application/pdf', as_attachment=False, download_name=f"{uuid}.pdf")
    finally: db.close()

def encounterGlaucomaReportByUUID(uuid: str):
    db = Session()
    try:
        result = (db.query(GlaucomaReport, PatientEncounters, ZipFile).join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id).join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id).filter(GlaucomaReport.uuid == uuid).first())
        if not result or not result[0].report_file_name:
            abort(404)
        glaucoma_report, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(GLAUCOMA_PDF_DIR / upload_date_str / glaucoma_report.report_file_name)
        if not os.path.exists(pdf_path_str):
            flash(f"Error: Glaucoma report not found with UUID: {uuid}", "danger")
            abort(404)
        return send_file(pdf_path_str, mimetype='application/pdf', as_attachment=False, download_name=f"{uuid}.pdf")
    finally: db.close()

def directImgOrigByUUID(uuid: str):
    db = Session()
    try:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not direct_image or not direct_image.filename: 
            abort(404)
        image_path_str = str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / direct_image.filename)
        if not os.path.exists(image_path_str): 
            flash(f"Error: Original Image not found with UUID: {uuid}", "danger")
            abort(404)
        file_extension = Path(direct_image.filename).suffix.lower()
        mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
        mimetype = mimetype_map.get(file_extension, 'image/jpeg')
        return send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}")
    finally: db.close()

def directImgEdByUUID(uuid: str):
    db = Session()
    try:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not direct_image or not direct_image.edited_filename: 
            flash(f"Error: No Edited Image for UUID: {uuid}", "danger")
            abort(404)
        image_path_str = str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / "edited" / direct_image.edited_filename)
        if not os.path.exists(image_path_str): 
            flash(f"Error: Edited Image not found with UUID: {uuid}", "danger")
            abort(404)
        file_extension = Path(direct_image.edited_filename).suffix.lower()
        mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
        mimetype = mimetype_map.get(file_extension, 'image/jpeg')
        return send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}")
    finally: db.close()

def directImgFinalByUUID(uuid: str):
    db = Session()
    try:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not direct_image or (not direct_image.filename and not direct_image.edited_filename): 
            flash(f"Error: Image not found with UUID: {uuid}", "danger")
            abort(404)
        if direct_image.edited_filename:
            image_path_str = str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / "edited" / direct_image.edited_filename)
            filename = direct_image.edited_filename
        else:
            image_path_str = str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / direct_image.filename)
            filename = direct_image.filename
        if not os.path.exists(image_path_str): 
            flash(f"Error: Image not found with UUID: {uuid}", "danger")
            abort(404)
        file_extension = Path(filename).suffix.lower()
        mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
        mimetype = mimetype_map.get(file_extension, 'image/jpeg')
        return send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}")
    finally: db.close()


def imgForGradingByUUID(uuid: str):
    """
    Serve an image for grading purposes by UUID.
    First tries to find an encounter image (from ZIP uploads),
    then tries to find a direct upload image (preferring edited versions).
    Shows appropriate error messages using flash if issues occur.
    Only one match is returned - encounter images have priority.
    """
    db = Session()
    try:
        # Check if both encounter image and direct upload image exist with the same UUID
        encounter_image = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        
        # If both exist, show error message
        if encounter_image and direct_image:
            flash(f"INTEGRITY ERROR: Two Images found with UUID: {uuid}" , "danger")
            abort(404)
        
        # If only encounter image exists, serve it
        if encounter_image:
            db.close()  # Close the session before calling the function
            return encounterImageByUUID(uuid)
        
        # If only direct image exists, serve it
        if direct_image:
            db.close()  # Close the session before calling the function
            return directImgFinalByUUID(uuid)
        
        # If neither exists, show error message
        flash(f"Error: Image not found with UUID: {uuid}", "danger")
        abort(404)
    finally:
        db.close()