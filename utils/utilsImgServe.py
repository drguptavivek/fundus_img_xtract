import os
from pathlib import Path
from typing import Tuple
from flask import send_file, abort, flash, make_response
from models import DirectImageVerify, Disease, EncounterFile, EncounterFilePDF, PatientEncounters, ZipFile, IMAGE_DIR, DiabeticRetinopathyReport, GlaucomaReport, PDF_DIR, DirectImageUpload, BASE_DIR, DR_PDF_DIR, GLAUCOMA_PDF_DIR, DIRECT_UPLOAD_DIR
from sqlalchemy import  and_, select
from db_transaction_manager import get_db_session




def encounterImageByUUID(uuid: str):
    with get_db_session() as db:
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
        
        response = make_response(send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}"))
        
        # Add cache control headers to prevent browser caching issues when images are updated
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response

def encounterDrReportByUUID(uuid: str):
    with get_db_session() as db:
        # Log PDF access request for debugging partitioned cookie issues
        from flask import current_app, request
        current_app.logger.info(f"DR PDF ACCESS REQUEST - UUID: {uuid}, Referer: {request.referrer}, User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        
        result = (db.query(DiabeticRetinopathyReport, PatientEncounters, ZipFile).join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id).join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id).filter(DiabeticRetinopathyReport.uuid == uuid).first())
        if not result or not result[0].report_file_name:
            current_app.logger.warning(f"DR PDF NOT FOUND - UUID: {uuid}")
            abort(404)
        dr_report, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(DR_PDF_DIR / upload_date_str / dr_report.report_file_name)
        if not os.path.exists(pdf_path_str):
            current_app.logger.error(f"DR PDF FILE MISSING - UUID: {uuid}, Path: {pdf_path_str}")
            flash(f"Error: DR report not found with UUID: {uuid}", "danger")
            abort(404)
        
        # Create response with security headers to prevent partitioned cookie warnings
        from flask import make_response
        response = make_response(send_file(pdf_path_str, mimetype='application/pdf', as_attachment=False, download_name=f"{uuid}.pdf"))
        
        # Fix CSP header - remove conflicting directives and allow same-origin
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self' http://127.0.0.1:5001; script-src 'self' 'unsafe-inline';"
        
        # Add proper CORS headers for same-origin requests
        origin = request.headers.get('Origin', 'http://127.0.0.1:5001')
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        
        # Add SameSite=None to allow cross-site access for same-origin iframes
        response.headers['Set-Cookie'] = 'SameSite=None; Secure; HttpOnly; Path=/'
        
        # Add explicit header to prevent partitioned cookie warnings
        response.headers['Sec-GPC'] = '1'  # Global Privacy Control
        response.headers['Partitioned-Cookie'] = '0'  # Explicitly disable partitioning
        
        # Cache control headers
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        current_app.logger.info(f"DR PDF SERVED - UUID: {uuid}, Fixed headers: CSP, CORS, SameSite=None, Anti-Partitioning")
        return response

def encounterGlaucomaReportByUUID(uuid: str):
    with get_db_session() as db:
        # Log PDF access request for debugging partitioned cookie issues
        from flask import current_app, request
        current_app.logger.info(f"PDF ACCESS REQUEST - UUID: {uuid}, Referer: {request.referrer}, User-Agent: {request.headers.get('User-Agent', 'Unknown')}")
        
        result = (db.query(GlaucomaReport, PatientEncounters, ZipFile).join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id).join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id).filter(GlaucomaReport.uuid == uuid).first())
        if not result or not result[0].report_file_name:
            current_app.logger.warning(f"PDF NOT FOUND - UUID: {uuid}")
            abort(404)
        glaucoma_report, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(GLAUCOMA_PDF_DIR / upload_date_str / glaucoma_report.report_file_name)
        if not os.path.exists(pdf_path_str):
            current_app.logger.error(f"PDF FILE MISSING - UUID: {uuid}, Path: {pdf_path_str}")
            flash(f"Error: Glaucoma report not found with UUID: {uuid}", "danger")
            abort(404)
        
        # Create response with security headers to prevent partitioned cookie warnings
        from flask import make_response
        response = make_response(send_file(pdf_path_str, mimetype='application/pdf', as_attachment=False, download_name=f"{uuid}.pdf"))
        
        # Fix CSP header - remove conflicting directives and allow same-origin
        # Use only frame-ancestors without x-frame-options to avoid conflicts
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self' http://127.0.0.1:5001; script-src 'self' 'unsafe-inline';"
        
        # Add proper CORS headers for same-origin requests
        origin = request.headers.get('Origin', 'http://127.0.0.1:5001')
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        
        # Add SameSite=None to allow cross-site access for same-origin iframes
        # This helps prevent partitioned cookie warnings in modern browsers
        response.headers['Set-Cookie'] = 'SameSite=None; Secure; HttpOnly; Path=/'
        
        # Add explicit header to prevent partitioned cookie warnings
        # This tells browsers not to partition cookies/storage for this request
        response.headers['Sec-GPC'] = '1'  # Global Privacy Control
        response.headers['Partitioned-Cookie'] = '0'  # Explicitly disable partitioning
        
        # Cache control headers
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        current_app.logger.info(f"PDF SERVED - UUID: {uuid}, Fixed headers: CSP, CORS, SameSite=None, Anti-Partitioning")
        return response

def encounterPDFByUUID(uuid: str):
    """
    Serve the original PDF file from an encounter by UUID.
    """
    with get_db_session() as db:
        result = (
            db.query(EncounterFilePDF, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFilePDF.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFilePDF.uuid == uuid)
            .first()
        )
        if not result or not result[0].filename:
            flash(f"Error: Encounter PDF not found with UUID: {uuid}", "danger")
            abort(404)
        
        pdf_file, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(PDF_DIR / upload_date_str / pdf_file.filename)
        
        if not os.path.exists(pdf_path_str):
            flash(f"Error: PDF file not found on disk: {uuid}", "danger")
            abort(404)
        
        return send_file(pdf_path_str, mimetype='application/pdf', as_attachment=False, download_name=f"{uuid}.pdf")

def directImgOrigByUUID(uuid: str):
    with get_db_session() as db:
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
        
        response = make_response(send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}"))
        
        # Add cache control headers to prevent browser caching issues when images are updated
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response

def directImgEdByUUID(uuid: str):
    with get_db_session() as db:
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
        
        response = make_response(send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}"))
        
        # Add cache control headers to prevent browser caching issues when images are updated
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response

def directImgFinalByUUID(uuid: str):
    with get_db_session() as db:
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
        
        from flask import make_response
        response = make_response(send_file(image_path_str, mimetype=mimetype, as_attachment=False, download_name=f"{uuid}{file_extension}"))
        
        # Add cache control headers to prevent browser caching issues when images are updated
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response


def imgForGradingByUUID(uuid: str):
    """
    Serve an image for grading purposes by UUID.
    First tries to find an encounter image (from ZIP uploads),
    then tries to find a direct upload image (preferring edited versions).
    Shows appropriate error messages using flash if issues occur.
    Only one match is returned - encounter images have priority.
    """
    with get_db_session() as db:
        # Check if both encounter image and direct upload image exist with the same UUID
        encounter_image = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        
        # If both exist, show error message
        if encounter_image and direct_image:
            flash(f"INTEGRITY ERROR: Two Images found with UUID: {uuid}" , "danger")
            abort(404)
        
        # If only encounter image exists, serve it
        if encounter_image:
            return encounterImageByUUID(uuid)
        
        # If only direct image exists, serve it
        if direct_image:
            return directImgFinalByUUID(uuid)
        
        # If neither exists, show error message
        flash(f"Error: Image not found with UUID: {uuid}", "danger")
        abort(404)
