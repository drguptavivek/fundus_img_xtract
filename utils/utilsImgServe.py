import os
from pathlib import Path
from typing import Tuple
from flask import send_file, abort, flash, make_response, current_app
from models import DirectImageVerify, Disease, EncounterFile, EncounterFilePDF, PatientEncounters, ZipFile, IMAGE_DIR, DiabeticRetinopathyReport, GlaucomaReport, PDF_DIR, DirectImageUpload, BASE_DIR, DR_PDF_DIR, GLAUCOMA_PDF_DIR, DIRECT_UPLOAD_DIR
from utils.fileUtils import (
    get_thumbnail_path_direct, get_thumbnail_path_encounter,
    thumbnail_exists_direct, thumbnail_exists_encounter,
    get_encounter_thumbnail_serving_path, get_direct_thumbnail_serving_path
)
from utils.image_processing import get_thumbnail_filename
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


# === Thumbnail Serving Functions ===

def encounterImageThumbnailByUUID(uuid: str):
    """Serve thumbnail for encounter (ZIP upload) images."""
    with get_db_session() as db:
        result = (db.query(EncounterFile, PatientEncounters, ZipFile)
                 .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                 .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                 .filter(EncounterFile.uuid == uuid).first())

        if not result or not result[0].filename:
            abort(404)

        encounter_file, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        original_image_path = IMAGE_DIR / upload_date_str / encounter_file.filename

        # Check if thumbnail exists and generate on-demand if missing
        if not thumbnail_exists_encounter(original_image_path):
            # Generate thumbnail on-demand
            try:
                from utils.image_processing import generate_thumbnail, get_thumbnail_filename
                thumbnail_filename = get_thumbnail_filename(original_image_path.name)
                thumbnail_path = original_image_path.parent / thumbnail_filename

                success = generate_thumbnail(original_image_path, thumbnail_path)
                if not success:
                    # If generation fails, fall back to original image
                    current_app.logger.warning(f"Failed to generate thumbnail for {original_image_path.name}")
                    return encounterImageByUUID(uuid)

            except Exception as e:
                # If generation fails, fall back to original image
                current_app.logger.error(f"Error generating thumbnail for {original_image_path.name}: {e}")
                return encounterImageByUUID(uuid)

        # Get thumbnail path
        try:
            thumbnail_dir, thumbnail_filename = get_encounter_thumbnail_serving_path(original_image_path)
            thumbnail_path = thumbnail_dir / thumbnail_filename

            if not thumbnail_path.exists():
                # Fallback to original image
                return encounterImageByUUID(uuid)

            file_extension = Path(thumbnail_filename).suffix.lower()
            mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                           '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
            mimetype = mimetype_map.get(file_extension, 'image/jpeg')

            response = make_response(send_file(
                str(thumbnail_path),
                mimetype=mimetype,
                as_attachment=False,
                download_name=f"thm_{uuid}{file_extension}"
            ))

            # Add cache headers for thumbnails (can be cached longer than original images)
            response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
            response.headers['X-Thumbnail'] = 'true'

            return response

        except Exception:
            # If any error occurs, fallback to original image
            return encounterImageByUUID(uuid)


def directImgOrigThumbnailByUUID(uuid: str):
    """Serve thumbnail for direct upload original images."""
    with get_db_session() as db:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not direct_image or not direct_image.filename:
            abort(404)

        # Check if thumbnail exists in database or on disk
        if (not direct_image.thumbnail_filename or
            not thumbnail_exists_direct(direct_image.folder_rel, direct_image.filename, 'orig')):
            # If thumbnail doesn't exist, serve the original image instead
            return directImgOrigByUUID(uuid)

        # Get thumbnail path
        try:
            thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(
                direct_image.folder_rel, direct_image.filename, 'orig'
            )
            thumbnail_path = thumbnail_dir / thumbnail_filename

            if not thumbnail_path.exists():
                # Fallback to original image
                return directImgOrigByUUID(uuid)

            file_extension = Path(thumbnail_filename).suffix.lower()
            mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                           '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
            mimetype = mimetype_map.get(file_extension, 'image/jpeg')

            response = make_response(send_file(
                str(thumbnail_path),
                mimetype=mimetype,
                as_attachment=False,
                download_name=f"thm_{uuid}{file_extension}"
            ))

            # Add cache headers for thumbnails
            response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
            response.headers['X-Thumbnail'] = 'true'

            return response

        except Exception:
            # If any error occurs, fallback to original image
            return directImgOrigByUUID(uuid)


def directImgEdThumbnailByUUID(uuid: str):
    """Serve thumbnail for direct upload edited images."""
    with get_db_session() as db:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not direct_image or not direct_image.edited_filename:
            abort(404)

        # Check if thumbnail exists in database or on disk
        if (not direct_image.edited_thumbnail_filename or
            not thumbnail_exists_direct(direct_image.folder_rel, direct_image.edited_filename, 'edited')):
            # If thumbnail doesn't exist, serve the edited image instead
            return directImgEdByUUID(uuid)

        # Get thumbnail path
        try:
            thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(
                direct_image.folder_rel, direct_image.edited_filename, 'edited'
            )
            thumbnail_path = thumbnail_dir / thumbnail_filename

            if not thumbnail_path.exists():
                # Fallback to edited image
                return directImgEdByUUID(uuid)

            file_extension = Path(thumbnail_filename).suffix.lower()
            mimetype_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
                           '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp'}
            mimetype = mimetype_map.get(file_extension, 'image/jpeg')

            response = make_response(send_file(
                str(thumbnail_path),
                mimetype=mimetype,
                as_attachment=False,
                download_name=f"thm_{uuid}{file_extension}"
            ))

            # Add cache headers for thumbnails
            response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
            response.headers['X-Thumbnail'] = 'true'

            return response

        except Exception:
            # If any error occurs, fallback to edited image
            return directImgEdByUUID(uuid)


def directImgFinalThumbnailByUUID(uuid: str):
    """
    Serve thumbnail for direct upload images (prefers edited if available, otherwise original).

    This follows the same logic as directImgFinalByUUID but for thumbnails.
    """
    with get_db_session() as db:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()
        if not direct_image or (not direct_image.filename and not direct_image.edited_filename):
            abort(404)

        # Try edited image thumbnail first
        if direct_image.edited_filename:
            if direct_image.edited_thumbnail_filename:
                return directImgEdThumbnailByUUID(uuid)
            else:
                # Generate edited thumbnail on-demand
                try:
                    from utils.fileUtils import abs_from_parts
                    from utils.image_processing import generate_thumbnail, get_thumbnail_filename

                    edited_path = abs_from_parts(direct_image.folder_rel, direct_image.edited_filename, kind='edited')
                    if edited_path.exists():
                        thumb_basename = get_thumbnail_filename(direct_image.edited_filename)
                        thumb_path = edited_path.parent / thumb_basename

                        success = generate_thumbnail(edited_path, thumb_path)
                        if success:
                            # Update database with thumbnail filename
                            direct_image.edited_thumbnail_filename = thumb_basename
                            db.commit()
                            return directImgEdThumbnailByUUID(uuid)
                except Exception as e:
                    current_app.logger.error(f"Error generating edited thumbnail on-demand: {e}")

        # Try original image thumbnail
        if direct_image.filename:
            if direct_image.thumbnail_filename:
                return directImgOrigThumbnailByUUID(uuid)
            else:
                # Generate original thumbnail on-demand
                try:
                    from utils.fileUtils import abs_from_parts
                    from utils.image_processing import generate_thumbnail, get_thumbnail_filename

                    orig_path = abs_from_parts(direct_image.folder_rel, direct_image.filename, kind='original')
                    if orig_path.exists():
                        thumb_basename = get_thumbnail_filename(direct_image.filename)
                        thumb_path = orig_path.parent / thumb_basename

                        success = generate_thumbnail(orig_path, thumb_path)
                        if success:
                            # Update database with thumbnail filename
                            direct_image.thumbnail_filename = thumb_basename
                            db.commit()
                            return directImgOrigThumbnailByUUID(uuid)
                except Exception as e:
                    current_app.logger.error(f"Error generating original thumbnail on-demand: {e}")

        # If both fail, fallback to original image logic
        return directImgFinalByUUID(uuid)


def universalImageThumbnailByUUID(uuid: str):
    """
    Universal thumbnail serving function that works for both encounter and direct upload images.

    This follows the same logic as imgForGradingByUUID but for thumbnails.
    """
    with get_db_session() as db:
        # Check if both encounter image and direct upload image exist with the same UUID
        encounter_image = db.query(EncounterFile).filter(EncounterFile.uuid == uuid).first()
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid).first()

        # If both exist, this is an integrity error
        if encounter_image and direct_image:
            abort(404)

        # If only encounter image exists, serve its thumbnail
        if encounter_image:
            return encounterImageThumbnailByUUID(uuid)

        # If only direct image exists, serve its thumbnail
        if direct_image:
            return directImgFinalThumbnailByUUID(uuid)

        # If neither exists, return 404
        abort(404)
