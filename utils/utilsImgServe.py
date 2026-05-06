import os
from pathlib import Path
from typing import Tuple
from flask import send_file, abort, flash, make_response, current_app, request
from flask_login import current_user
from werkzeug.exceptions import NotFound
from models import (
    DirectImageVerify, Disease, EncounterFile, EncounterFilePDF, PatientEncounters, ZipFile, IMAGE_DIR,
    DiabeticRetinopathyReport, GlaucomaReport, PDF_DIR, DirectImageUpload, BASE_DIR, DR_PDF_DIR,
    GLAUCOMA_PDF_DIR, DIRECT_UPLOAD_DIR, EncounterSetImage, UserDiseaseUnitRole, GradingTask
)
from utils.fileUtils import (
    get_thumbnail_path_direct, get_thumbnail_path_encounter,
    thumbnail_exists_direct, thumbnail_exists_encounter,
    get_encounter_thumbnail_serving_path, get_direct_thumbnail_serving_path
)
from utils.image_processing import get_thumbnail_filename
from utils.log_sanitize import sanitize_log_value
from utils.hospital_scoping import apply_scoping, determine_scoping_context
from utils.media_cache import bump_media_cache_version
from sqlalchemy import and_, select, or_
from db_transaction_manager import transaction_scope
from utils.linkedGradingUtils import get_primary_disease_id


def _build_image_response(
    image_path_str: str,
    filename: str,
    uuid: str,
    *,
    cache_control: str,
    extra_headers: dict[str, str] | None = None,
    add_no_cache_headers: bool = False,
    download_name: str | None = None,
):
    file_extension = Path(filename).suffix.lower()
    mimetype_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
    }
    mimetype = mimetype_map.get(file_extension, 'image/jpeg')

    if download_name is None:
        download_name = f"{uuid}{file_extension}"
    response = make_response(
        send_file(
            image_path_str,
            mimetype=mimetype,
            as_attachment=False,
            download_name=download_name,
        )
    )
    response.headers['Cache-Control'] = cache_control
    if add_no_cache_headers:
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    if extra_headers:
        for key, value in extra_headers.items():
            response.headers[key] = value
    return response


def _direct_image_path(direct_image: DirectImageUpload, kind: str) -> tuple[str, str] | None:
    if kind == "edited":
        if not direct_image.edited_filename:
            return None
        filename = direct_image.edited_filename
        return str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / "edited" / filename), filename
    if kind == "orig":
        if not direct_image.filename:
            return None
        filename = direct_image.filename
        return str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / filename), filename
    if kind == "final":
        if direct_image.edited_filename:
            filename = direct_image.edited_filename
            return str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / "edited" / filename), filename
        if direct_image.filename:
            filename = direct_image.filename
            return str(DIRECT_UPLOAD_DIR / direct_image.folder_rel / filename), filename
        return None
    return None


def _serve_encounter_image(encounter_file: EncounterFile, zip_file: ZipFile, uuid: str):
    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
    image_path_str = str(IMAGE_DIR / upload_date_str / encounter_file.filename)
    if not os.path.exists(image_path_str):
        abort(404)
    return _build_image_response(
        image_path_str,
        encounter_file.filename,
        uuid,
        cache_control='private, max-age=60',
    )


def _serve_encounter_thumbnail(encounter_file: EncounterFile, zip_file: ZipFile, uuid: str):
    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
    original_image_path = IMAGE_DIR / upload_date_str / encounter_file.filename

    if not thumbnail_exists_encounter(original_image_path):
        try:
            from utils.image_processing import generate_thumbnail
            thumbnail_filename = get_thumbnail_filename(original_image_path.name)
            thumbnail_path = original_image_path.parent / thumbnail_filename

            success = generate_thumbnail(original_image_path, thumbnail_path)
            if not success:
                current_app.logger.warning(
                    "Failed to generate thumbnail for %s",
                    sanitize_log_value(original_image_path.name),
                )
                return _serve_encounter_image(encounter_file, zip_file, uuid)
            bump_media_cache_version(uuid)
        except Exception as e:
            current_app.logger.error(
                "Error generating thumbnail for %s: %s",
                sanitize_log_value(original_image_path.name),
                sanitize_log_value(e),
            )
            return _serve_encounter_image(encounter_file, zip_file, uuid)

    try:
        thumbnail_dir, thumbnail_filename = get_encounter_thumbnail_serving_path(original_image_path)
        thumbnail_path = thumbnail_dir / thumbnail_filename

        if not thumbnail_path.exists():
            return _serve_encounter_image(encounter_file, zip_file, uuid)

        return _build_image_response(
            str(thumbnail_path),
            thumbnail_filename,
            uuid,
            cache_control='private, max-age=60',
            extra_headers={'X-Thumbnail': 'true'},
            download_name=f"thm_{uuid}{thumbnail_path.suffix.lower()}",
        )
    except Exception:
        return _serve_encounter_image(encounter_file, zip_file, uuid)


def _user_has_grading_slot(db, user, lab_unit_id: int | None, disease_id: int | None) -> bool:
    """Check if the user has any grading slot for the lab unit + disease."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not lab_unit_id or not disease_id:
        return False

    effective_disease_id = get_primary_disease_id(db, disease_id)
    disease_ids = {disease_id, effective_disease_id}
    return (
        db.query(UserDiseaseUnitRole)
        .filter(
            UserDiseaseUnitRole.user_id == user.id,
            UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
            UserDiseaseUnitRole.disease_id.in_(disease_ids),
            UserDiseaseUnitRole.active == True,
            or_(
                UserDiseaseUnitRole.can_grade_resident == True,
                UserDiseaseUnitRole.can_grade_resident2 == True,
                UserDiseaseUnitRole.can_arbitrate == True,
            ),
        )
        .first()
        is not None
    )


def _user_has_grading_access_to_image(db, user, uuid: str) -> bool:
    """Check grading slot access across all tasks linked to an image UUID."""
    tasks = (
        db.query(GradingTask.lab_unit_id, GradingTask.disease_id)
        .join(EncounterFile, GradingTask.encounter_file_id == EncounterFile.id)
        .filter(EncounterFile.uuid == uuid)
        .all()
    )
    if not tasks:
        tasks = (
            db.query(GradingTask.lab_unit_id, GradingTask.disease_id)
            .join(DirectImageUpload, GradingTask.direct_image_upload_id == DirectImageUpload.id)
            .filter(DirectImageUpload.uuid == uuid)
            .all()
        )

    return any(
        _user_has_grading_slot(db, user, lab_unit_id, disease_id)
        for lab_unit_id, disease_id in tasks
    )


def _apply_lab_unit_scoping(query, model_class, user):
    """Restrict query to user's lab units (non-grading access)."""
    if not user:
        return query

    def apply_filter(q, *args):
        if hasattr(q, "filter"):
            return q.filter(*args)
        return q.where(*args)

    lab_unit_ids = [lu.id for lu in (user.lab_units or [])]
    if not lab_unit_ids:
        return apply_filter(query, model_class.id == None)

    if hasattr(model_class, "lab_unit_id"):
        return apply_filter(query, model_class.lab_unit_id.in_(lab_unit_ids))

    return query


def _serve_direct_image(direct_image: DirectImageUpload, uuid: str, kind: str):
    path_info = _direct_image_path(direct_image, kind)
    if not path_info:
        return None
    image_path_str, filename = path_info
    if not os.path.exists(image_path_str):
        return None
    return _build_image_response(
        image_path_str,
        filename,
        uuid,
        cache_control='private, max-age=60',
    )




def encounterImageByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)
        
    context = determine_scoping_context()
    
    with transaction_scope() as db:
        query = db.query(EncounterFile, PatientEncounters, ZipFile)
        query = query.join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        query = query.join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        query = query.filter(EncounterFile.uuid == uuid)
        
        # Apply dynamic scoping
        query = apply_scoping(query, PatientEncounters, current_user, context)
        
        result = query.first()

        
        if not result or not result[0].filename:
            # If scoped out or not found
            # flash message? Original code did.
            # flash(f"Error: Encounter image not found with UUID: {uuid}", "danger")
            abort(404)
            
        encounter_file, patient_encounter, zip_file = result
        
        return _serve_encounter_image(encounter_file, zip_file, uuid)

def encounterDrReportByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)

    context = determine_scoping_context()

    with transaction_scope() as db:
        # Log PDF access request for debugging partitioned cookie issues
        from flask import current_app, request
        current_app.logger.info(
            "DR PDF ACCESS REQUEST - UUID: %s, Referer: %s, User-Agent: %s",
            sanitize_log_value(uuid),
            sanitize_log_value(request.referrer),
            sanitize_log_value(request.headers.get("User-Agent", "Unknown")),
        )

        query = (db.query(DiabeticRetinopathyReport, PatientEncounters, ZipFile)
                 .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                 .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                 .filter(DiabeticRetinopathyReport.uuid == uuid))

        # Apply hospital scoping for security
        query = apply_scoping(query, PatientEncounters, current_user, context)
        result = query.first()
        if not result or not result[0].report_file_name:
            current_app.logger.warning(
                "DR PDF NOT FOUND - UUID: %s",
                sanitize_log_value(uuid),
            )
            abort(404)
        dr_report, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(DR_PDF_DIR / upload_date_str / dr_report.report_file_name)
        if not os.path.exists(pdf_path_str):
            current_app.logger.error(
                "DR PDF FILE MISSING - UUID: %s, Path: %s",
                sanitize_log_value(uuid),
                sanitize_log_value(pdf_path_str),
            )
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
        
        current_app.logger.info(
            "DR PDF SERVED - UUID: %s, Fixed headers: CSP, CORS, SameSite=None, Anti-Partitioning",
            sanitize_log_value(uuid),
        )
        return response

def encounterGlaucomaReportByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)

    context = determine_scoping_context()

    with transaction_scope() as db:
        # Log PDF access request for debugging partitioned cookie issues
        from flask import current_app, request
        current_app.logger.info(
            "PDF ACCESS REQUEST - UUID: %s, Referer: %s, User-Agent: %s",
            sanitize_log_value(uuid),
            sanitize_log_value(request.referrer),
            sanitize_log_value(request.headers.get("User-Agent", "Unknown")),
        )

        query = (db.query(GlaucomaReport, PatientEncounters, ZipFile)
                 .join(PatientEncounters, GlaucomaReport.patient_encounter_id == PatientEncounters.id)
                 .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                 .filter(GlaucomaReport.uuid == uuid))

        # Apply hospital scoping for security
        query = apply_scoping(query, PatientEncounters, current_user, context)
        result = query.first()
        if not result or not result[0].report_file_name:
            current_app.logger.warning(
                "PDF NOT FOUND - UUID: %s",
                sanitize_log_value(uuid),
            )
            abort(404)
        glaucoma_report, patient_encounter, zip_file = result
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        pdf_path_str = str(GLAUCOMA_PDF_DIR / upload_date_str / glaucoma_report.report_file_name)
        if not os.path.exists(pdf_path_str):
            current_app.logger.error(
                "PDF FILE MISSING - UUID: %s, Path: %s",
                sanitize_log_value(uuid),
                sanitize_log_value(pdf_path_str),
            )
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
        
        current_app.logger.info(
            "PDF SERVED - UUID: %s, Fixed headers: CSP, CORS, SameSite=None, Anti-Partitioning",
            sanitize_log_value(uuid),
        )
        return response

def encounterPDFByUUID(uuid: str):
    """
    Serve the original PDF file from an encounter by UUID.
    """
    if not current_user or not current_user.is_authenticated:
        abort(401)

    context = determine_scoping_context()

    with transaction_scope() as db:
        query = (
            db.query(EncounterFilePDF, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFilePDF.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFilePDF.uuid == uuid)
        )

        # Apply hospital scoping for security
        query = apply_scoping(query, PatientEncounters, current_user, context)
        result = query.first()
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
    if not current_user or not current_user.is_authenticated:
        abort(401)
    
    context = determine_scoping_context()
        
    with transaction_scope() as db:
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        query = apply_scoping(query, DirectImageUpload, current_user, context)
        direct_image = query.first()
        
        if not direct_image or not direct_image.filename:
            abort(404)
        response = _serve_direct_image(direct_image, uuid, "orig")
        if response:
            return response
        flash(f"Error: Original Image not found with UUID: {uuid}", "danger")
        abort(404)

def directImgEdByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)

    context = determine_scoping_context()
        
    with transaction_scope() as db:
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        query = apply_scoping(query, DirectImageUpload, current_user, context)
        direct_image = query.first()
        
        if not direct_image or not direct_image.edited_filename:
            flash(f"Error: No Edited Image for UUID: {uuid}", "danger")
            abort(404)
        response = _serve_direct_image(direct_image, uuid, "edited")
        if response:
            return response
        flash(f"Error: Edited Image not found with UUID: {uuid}", "danger")
        abort(404)

def directImgFinalByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)
    
    context = determine_scoping_context()
        
    with transaction_scope() as db:
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        query = apply_scoping(query, DirectImageUpload, current_user, context)
        direct_image = query.first()
        
        if not direct_image or (not direct_image.filename and not direct_image.edited_filename):
            flash(f"Error: Image not found with UUID: {uuid}", "danger")
            abort(404)
        response = _serve_direct_image(direct_image, uuid, "final")
        if response:
            return response
        flash(f"Error: Image not found with UUID: {uuid}", "danger")
        abort(404)


def imgForGradingByUUID(uuid: str):
    """
    Serve an image for grading purposes by UUID.
    First tries to find an encounter image (from ZIP uploads),
    then tries to find a direct upload image (preferring edited versions).
    Shows appropriate error messages using flash if issues occur.
    Only one match is returned - encounter images have priority.
    """
    if not current_user or not current_user.is_authenticated:
        abort(401)

    with transaction_scope() as db:
        allow_grading_access = _user_has_grading_access_to_image(db, current_user, uuid)

        encounter_query = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid == uuid)
        )
        if not allow_grading_access:
            encounter_query = _apply_lab_unit_scoping(encounter_query, PatientEncounters, current_user)
        encounter_result = encounter_query.first()

        direct_query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        if not allow_grading_access:
            direct_query = _apply_lab_unit_scoping(direct_query, DirectImageUpload, current_user)
        direct_image = direct_query.first()

        if encounter_result and direct_image:
            flash(f"INTEGRITY ERROR: Two Images found with UUID: {uuid}", "danger")
            abort(404)

        if encounter_result:
            encounter_file, patient_encounter, zip_file = encounter_result
            if not encounter_file or not encounter_file.filename:
                abort(404)
            return _serve_encounter_image(encounter_file, zip_file, uuid)

        if direct_image:
            response = _serve_direct_image(direct_image, uuid, "final")
            if response:
                return response
            flash(f"Error: Image not found with UUID: {uuid}", "danger")
            abort(404)

        flash(f"Error: Image not found with UUID: {uuid}", "danger")
        abort(404)


# === Thumbnail Serving Functions ===

def encounterImageThumbnailByUUID(uuid: str):
    """Serve thumbnail for encounter (ZIP upload) images."""
    if not current_user or not current_user.is_authenticated:
        abort(401)
        
    context = determine_scoping_context()
    
    with transaction_scope() as db:
        query = (db.query(EncounterFile, PatientEncounters, ZipFile)
                 .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                 .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
                 .filter(EncounterFile.uuid == uuid))
                 
        # Apply dynamic scoping
        query = apply_scoping(query, PatientEncounters, current_user, context)
        result = query.first()

        if not result or not result[0].filename:
            abort(404)

        encounter_file, patient_encounter, zip_file = result
        return _serve_encounter_thumbnail(encounter_file, zip_file, uuid)


def directImgOrigThumbnailByUUID(uuid: str):
    """Serve thumbnail for direct upload original images."""
    if not current_user or not current_user.is_authenticated:
        abort(401)
        
    context = determine_scoping_context()
    
    with transaction_scope() as db:
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        query = apply_scoping(query, DirectImageUpload, current_user, context)
        direct_image = query.first()
        
        if not direct_image or not direct_image.filename:
            abort(404)

        # 1. Try to serve existing thumbnail
        try:
            thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(
                direct_image.folder_rel, direct_image.filename, 'orig'
            )
            thumbnail_path = thumbnail_dir / thumbnail_filename

            if thumbnail_path.exists():
                return _build_image_response(
                    str(thumbnail_path),
                    thumbnail_filename,
                    uuid,
                    cache_control='private, max-age=60',
                    extra_headers={'X-Thumbnail': 'true'},
                    download_name=f"thm_{uuid}{thumbnail_path.suffix.lower()}",
                )
        except Exception:
            pass

        # 2. If not exists, try to generate on-demand
        try:
            from utils.fileUtils import abs_from_parts
            from utils.image_processing import generate_thumbnail, get_thumbnail_filename

            orig_path = abs_from_parts(direct_image.folder_rel, direct_image.filename, kind='orig')
            if orig_path.exists():
                thumb_basename = get_thumbnail_filename(direct_image.filename)
                thumb_path = orig_path.parent / thumb_basename

                success = generate_thumbnail(orig_path, thumb_path)
                if success:
                    direct_image.thumbnail_filename = thumb_basename
                    bump_media_cache_version(uuid)
                    return _build_image_response(
                        str(thumb_path),
                        thumb_basename,
                        uuid,
                        cache_control='private, max-age=60',
                        extra_headers={'X-Thumbnail': 'true'},
                        download_name=f"thm_{uuid}{thumb_path.suffix.lower()}",
                    )
        except Exception as e:
            current_app.logger.error(f"Error generating thumbnail on-demand for {uuid}: {e}")

        # 3. Last resort fallback: serve full image (safely)
        response = _serve_direct_image(direct_image, uuid, "orig")
        if response:
            return response
        abort(404)


def directImgEdThumbnailByUUID(uuid: str):
    """Serve thumbnail for direct upload edited images."""
    if not current_user or not current_user.is_authenticated:
        abort(401)
        
    context = determine_scoping_context()
    
    with transaction_scope() as db:
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        query = apply_scoping(query, DirectImageUpload, current_user, context)
        direct_image = query.first()
        
        if not direct_image or not direct_image.edited_filename:
            abort(404)

        # 1. Try to serve existing thumbnail
        try:
            thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(
                direct_image.folder_rel, direct_image.edited_filename, 'edited'
            )
            thumbnail_path = thumbnail_dir / thumbnail_filename

            if thumbnail_path.exists():
                return _build_image_response(
                    str(thumbnail_path),
                    thumbnail_filename,
                    uuid,
                    cache_control='private, max-age=60',
                    extra_headers={'X-Thumbnail': 'true'},
                    download_name=f"thm_{uuid}{thumbnail_path.suffix.lower()}",
                )
        except Exception:
            pass

        # 2. If not exists, try to generate on-demand
        try:
            from utils.fileUtils import abs_from_parts
            from utils.image_processing import generate_thumbnail, get_thumbnail_filename

            edited_path = abs_from_parts(direct_image.folder_rel, direct_image.edited_filename, kind='edited')
            if edited_path.exists():
                thumb_basename = get_thumbnail_filename(direct_image.edited_filename)
                thumb_path = edited_path.parent / thumb_basename

                success = generate_thumbnail(edited_path, thumb_path)
                if success:
                    direct_image.edited_thumbnail_filename = thumb_basename
                    bump_media_cache_version(uuid)
                    return _build_image_response(
                        str(thumb_path),
                        thumb_basename,
                        uuid,
                        cache_control='private, max-age=60',
                        extra_headers={'X-Thumbnail': 'true'},
                        download_name=f"thm_{uuid}{thumb_path.suffix.lower()}",
                    )
        except Exception as e:
            current_app.logger.error(f"Error generating edited thumbnail on-demand for {uuid}: {e}")

        # 3. Last resort fallback: serve full image (safely)
        response = _serve_direct_image(direct_image, uuid, "edited")
        if response:
            return response
        abort(404)


def _serve_direct_final_thumbnail(db, direct_image: DirectImageUpload, uuid: str):
    def _serve_direct_thumbnail(folder_rel: str, original_filename: str, kind: str):
        try:
            thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(
                folder_rel, original_filename, kind
            )
            thumbnail_path = thumbnail_dir / thumbnail_filename
            if not thumbnail_path.exists():
                return None

            return _build_image_response(
                str(thumbnail_path),
                thumbnail_filename,
                uuid,
                cache_control='private, max-age=60',
                extra_headers={'X-Thumbnail': 'true'},
                download_name=f"thm_{uuid}{thumbnail_path.suffix.lower()}",
            )
        except Exception as e:
            current_app.logger.error(
                "Error serving direct thumbnail inline: %s",
                sanitize_log_value(e),
            )
            return None

    if not direct_image or (not direct_image.filename and not direct_image.edited_filename):
        abort(404)

    if direct_image.edited_filename:
        if direct_image.edited_thumbnail_filename:
            served = _serve_direct_thumbnail(
                direct_image.folder_rel, direct_image.edited_filename, "edited"
            )
            if served:
                return served
        else:
            try:
                from utils.fileUtils import abs_from_parts
                from utils.image_processing import generate_thumbnail, get_thumbnail_filename

                edited_path = abs_from_parts(direct_image.folder_rel, direct_image.edited_filename, kind='edited')
                if edited_path.exists():
                    thumb_basename = get_thumbnail_filename(direct_image.edited_filename)
                    thumb_path = edited_path.parent / thumb_basename

                    success = generate_thumbnail(edited_path, thumb_path)
                    if success:
                        direct_image.edited_thumbnail_filename = thumb_basename
                        bump_media_cache_version(uuid)
                        served = _serve_direct_thumbnail(
                            direct_image.folder_rel, direct_image.edited_filename, "edited"
                        )
                        if served:
                            return served
            except Exception as e:
                current_app.logger.error(
                    "Error generating edited thumbnail on-demand: %s",
                    sanitize_log_value(e),
                )

    if direct_image.filename:
        if direct_image.thumbnail_filename:
            served = _serve_direct_thumbnail(
                direct_image.folder_rel, direct_image.filename, "orig"
            )
            if served:
                return served
        else:
            try:
                from utils.fileUtils import abs_from_parts
                from utils.image_processing import generate_thumbnail, get_thumbnail_filename

                orig_path = abs_from_parts(direct_image.folder_rel, direct_image.filename, kind='original')
                if orig_path.exists():
                    thumb_basename = get_thumbnail_filename(direct_image.filename)
                    thumb_path = orig_path.parent / thumb_basename

                    success = generate_thumbnail(orig_path, thumb_path)
                    if success:
                        direct_image.thumbnail_filename = thumb_basename
                        bump_media_cache_version(uuid)
                        served = _serve_direct_thumbnail(
                            direct_image.folder_rel, direct_image.filename, "orig"
                        )
                        if served:
                            return served
            except Exception as e:
                current_app.logger.error(
                    "Error generating original thumbnail on-demand: %s",
                    sanitize_log_value(e),
                )

    response = _serve_direct_image(direct_image, uuid, "final")
    if response:
        return response
    flash(f"Error: Image not found with UUID: {uuid}", "danger")
    abort(404)


def directImgFinalThumbnailByUUID(uuid: str):
    """
    Serve thumbnail for direct upload images (prefers edited if available, otherwise original).

    This follows the same logic as directImgFinalByUUID but for thumbnails.
    """
    with transaction_scope() as db:
        if not current_user or not current_user.is_authenticated:
            abort(401)
            
        context = determine_scoping_context()
        
        query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        query = apply_scoping(query, DirectImageUpload, current_user, context)
        direct_image = query.first()

        return _serve_direct_final_thumbnail(db, direct_image, uuid)


def universalImageThumbnailByUUID(uuid: str):
    """
    Universal thumbnail serving function that works for both encounter and direct upload images.

    This follows the same logic as imgForGradingByUUID but for thumbnails.
    """
    if not current_user or not current_user.is_authenticated:
        abort(401)

    with transaction_scope() as db:
        lab_unit_id, disease_id = _get_grading_task_context_for_image(db, uuid)
        allow_grading_access = _user_has_grading_slot(db, current_user, lab_unit_id, disease_id)

        encounter_query = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid == uuid)
        )
        if not allow_grading_access:
            encounter_query = _apply_lab_unit_scoping(encounter_query, PatientEncounters, current_user)
        encounter_result = encounter_query.first()

        direct_query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid)
        if not allow_grading_access:
            direct_query = _apply_lab_unit_scoping(direct_query, DirectImageUpload, current_user)
        direct_image = direct_query.first()

        if encounter_result and direct_image:
            abort(404)

        if encounter_result:
            encounter_file, patient_encounter, zip_file = encounter_result
            if not encounter_file or not encounter_file.filename:
                abort(404)
            return _serve_encounter_thumbnail(encounter_file, zip_file, uuid)

        if direct_image:
            return _serve_direct_final_thumbnail(db, direct_image, uuid)

        abort(404)

def _serve_encounter_set_image(img: EncounterSetImage, uuid: str):
    # folder_rel is already relative to BASE_DIR
    image_path_str = str(BASE_DIR / img.folder_rel / img.original_filename)
    if not os.path.exists(image_path_str):
        abort(404)
    return _build_image_response(
        image_path_str,
        img.original_filename,
        uuid,
        cache_control='no-cache, no-store, must-revalidate',
        add_no_cache_headers=True,
    )

def encounterSetImageByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)
    context = determine_scoping_context()
    with transaction_scope() as db:
        query = db.query(EncounterSetImage).join(PatientEncounters).filter(EncounterSetImage.uuid == uuid)
        query = apply_scoping(query, PatientEncounters, current_user, context)
        img = query.first()
        if not img:
            abort(404)
        return _serve_encounter_set_image(img, uuid)

def encounterSetImageThumbnailByUUID(uuid: str):
    if not current_user or not current_user.is_authenticated:
        abort(401)
    context = determine_scoping_context()
    with transaction_scope() as db:
        query = db.query(EncounterSetImage).join(PatientEncounters).filter(EncounterSetImage.uuid == uuid)
        query = apply_scoping(query, PatientEncounters, current_user, context)
        img = query.first()
        if not img:
            abort(404)
        
        # If thumbnail exists, serve it
        if img.thumbnail_filename:
            thumb_path = BASE_DIR / img.folder_rel / "thumbnails" / img.thumbnail_filename
            if thumb_path.exists():
                return _build_image_response(
                    str(thumb_path),
                    img.thumbnail_filename,
                    uuid,
                    cache_control='private, max-age=60',
                    extra_headers={'X-Thumbnail': 'true'},
                )
        
        # Fallback to full image for now
        return _serve_encounter_set_image(img, uuid)


def encounterSetImageEditedByUUID(uuid: str):
    """Serve edited encounter set image by UUID (if exists, else 404)."""
    if not current_user or not current_user.is_authenticated:
        abort(401)
    context = determine_scoping_context()
    with transaction_scope() as db:
        query = db.query(EncounterSetImage).join(PatientEncounters).filter(EncounterSetImage.uuid == uuid)
        query = apply_scoping(query, PatientEncounters, current_user, context)
        img = query.first()
        if not img:
            abort(404)
        if not img.edited_filename:
            abort(404, description="No edited version exists")

        # Serve the edited version
        image_path_str = str(BASE_DIR / img.folder_rel / img.edited_filename)
        if not os.path.exists(image_path_str):
            abort(404)
        return _build_image_response(
            image_path_str,
            img.edited_filename,
            uuid,
            cache_control='no-cache, no-store, must-revalidate',
            add_no_cache_headers=True,
        )
