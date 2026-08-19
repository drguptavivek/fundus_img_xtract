import os
import logging
import jwt
from datetime import datetime, timedelta, timezone
from flask import jsonify, request, current_app
from uuid import uuid4
from functools import wraps
from io import BytesIO
from PIL import Image
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

from . import api_bp
from db_transaction_manager import transaction_scope
from models import PatientEncounters, EncounterSetImage, User
from upload_profiles.models import PatientEncounterTargetDisease
from auth.utils import utcnow
from auth.decorators import token_auth_required
from services.encounter_referral_suggestion import normalize_referral_positive_diseases, normalize_referral_suggestion
from services.encounter_set_ai_inference import enqueue_wadhwani_for_encounter_ids
from utils.rate_limiter import api_rate_limit
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("api.encounter_set")

from flask_login import login_required, current_user
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from auth.roles import roles_or_project_grant_required
from utils.hospital_scoping import apply_scoping
from upload_profiles.service import (
    UPLOAD_KIND_ENCOUNTER_SET,
    UploadProfileError,
    encounter_set_grading_scheme_ids,
    validate_profile_upload_scope,
)
from encounter_sets.monocular_status import update_monocular_status


@api_bp.route("/encounter-sets/<uuid>/monocular-status", methods=["PATCH"])
@roles_or_project_grant_required("admin", "optometrist", "data_manager")
def patch_encounter_set_monocular_status(uuid):
    """Correct canonical monocular status before or after verification."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload.get("is_monocular"), bool):
        return jsonify(success=False, error="is_monocular must be a boolean."), 400
    result = update_monocular_status(
        encounter_uuid=uuid,
        is_monocular=payload["is_monocular"],
        user=current_user,
    )
    return jsonify(
        success=result.success,
        message=result.message,
        error=None if result.success else result.message,
        encounter_uuid=result.encounter_uuid,
        is_monocular=result.is_monocular,
    ), result.status_code

# ============================================================================
# FILE VALIDATION CONFIGURATION
# ============================================================================

# Whitelist of allowed file extensions (case-insensitive)
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}

# Allowed MIME types for each extension
ALLOWED_MIME_TYPES = {
    '.jpg': {'image/jpeg', 'image/jpg'},
    '.jpeg': {'image/jpeg', 'image/jpg'},
    '.png': {'image/png'},
    '.gif': {'image/gif'},
    '.bmp': {'image/bmp'},
}

# Magic bytes (file signatures) for validation
MAGIC_BYTES = {
    b'\xFF\xD8\xFF\xE0': ('.jpg', 'image/jpeg'),  # JPEG SOI
    b'\xFF\xD8\xFF\xE1': ('.jpg', 'image/jpeg'),  # JPEG EXIF
    b'\x89PNG\r\n\x1a\n': ('.png', 'image/png'),  # PNG
    b'GIF87a': ('.gif', 'image/gif'),              # GIF87a
    b'GIF89a': ('.gif', 'image/gif'),              # GIF89a
    b'BM': ('.bmp', 'image/bmp'),                  # BMP
}

# Max file size: 50 MB
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_DIMENSION = 10000  # Max width/height in pixels


def validate_image_file(file_obj):
    """
    Comprehensive image file validation:
    1. File size limits
    2. File extension whitelist
    3. Magic byte verification
    4. MIME type validation
    5. Actual image content verification

    Args:
        file_obj: werkzeug FileStorage object

    Returns:
        Tuple of (is_valid, error_message)
    """
    # =========================================================================
    # STEP 0: FILE SIZE VALIDATION (P1.2)
    # =========================================================================

    # Check file size before processing (prevent DoS/disk exhaustion)
    if hasattr(file_obj, 'content_length') and file_obj.content_length:
        if file_obj.content_length > MAX_FILE_SIZE_BYTES:
            logger.warning(
                "File size exceeds limit",
                extra={
                    'filename': sanitize_log_value(file_obj.filename),
                    'size_bytes': file_obj.content_length,
                    'limit_bytes': MAX_FILE_SIZE_BYTES
                }
            )
            max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
            return False, f"File size exceeds maximum limit of {max_mb:.0f}MB"

    # =========================================================================
    # STEP 1: FILENAME VALIDATION
    # =========================================================================

    if not file_obj.filename:
        return False, "No filename provided"

    # Check for null bytes and other suspicious patterns
    if '\x00' in file_obj.filename:
        logger.warning("Null byte in filename: %s", sanitize_log_value(file_obj.filename))
        return False, "Invalid filename"

    # Get extension (case-insensitive)
    filename_lower = file_obj.filename.lower()
    if '.' not in filename_lower:
        return False, "File must have an extension (.jpg, .png, .gif, or .bmp)"

    ext = os.path.splitext(filename_lower)[1]

    # Whitelist extension check
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        logger.warning(
            "Upload rejected: invalid extension",
            extra={'extension': ext, 'filename': sanitize_log_value(file_obj.filename)}
        )
        return False, f"Invalid file format. Only JPG, PNG, GIF, BMP files are allowed"

    # =========================================================================
    # STEP 2: FILE SIZE VALIDATION
    # =========================================================================

    file_obj.seek(0, 2)  # Seek to end
    file_size = file_obj.tell()
    file_obj.seek(0)  # Reset to beginning

    if file_size == 0:
        return False, "File is empty"

    if file_size > MAX_FILE_SIZE_BYTES:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)}MB"

    # =========================================================================
    # STEP 3: MAGIC BYTE VALIDATION (File Signature)
    # =========================================================================

    file_content = file_obj.read()
    file_obj.seek(0)  # Reset for later use

    magic_valid = False
    detected_ext = None
    detected_mime = None

    for magic_bytes, (ext_match, mime_match) in MAGIC_BYTES.items():
        if file_content.startswith(magic_bytes):
            magic_valid = True
            detected_ext = ext_match
            detected_mime = mime_match
            break

    if not magic_valid:
        logger.warning(
            "Invalid magic bytes for file",
            extra={'filename': sanitize_log_value(file_obj.filename)}
        )
        return False, "Invalid image file. File is not a valid image"

    # =========================================================================
    # STEP 4: MIME TYPE VALIDATION
    # =========================================================================

    content_type = file_obj.content_type or 'application/octet-stream'

    # Check if provided MIME type matches allowed types for this extension
    allowed_mimes = ALLOWED_MIME_TYPES.get(ext, set())

    if content_type not in allowed_mimes and content_type.lower() not in allowed_mimes:
        logger.warning(
            "Invalid MIME type for extension",
            extra={
                'extension': ext,
                'content_type': content_type,
                'filename': sanitize_log_value(file_obj.filename)
            }
        )
        return False, f"Invalid MIME type {content_type} for {ext} file"

    # =========================================================================
    # STEP 5: IMAGE CONTENT VERIFICATION (PIL)
    # =========================================================================

    try:
        file_obj.seek(0)
        with Image.open(BytesIO(file_content)) as img:
            # Verify image format matches magic bytes
            if img.format:
                img_format = img.format.lower()
                # Map PIL format to extension
                format_to_ext = {
                    'jpeg': '.jpg',
                    'jpg': '.jpg',
                    'png': '.png',
                    'gif': '.gif',
                    'bmp': '.bmp',
                }
                detected_format = format_to_ext.get(img_format)

                if detected_format and detected_format != ext:
                    logger.warning(
                        "File extension mismatch with actual format",
                        extra={
                            'extension': ext,
                            'actual_format': img_format,
                            'filename': sanitize_log_value(file_obj.filename)
                        }
                    )
                    # Don't reject, just log (some valid images might have wrong ext)

            # Check image dimensions (prevent decompression bombs)
            width, height = img.size
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                logger.warning(
                    "Image dimensions exceed maximum",
                    extra={'width': width, 'height': height}
                )
                return False, f"Image too large. Maximum dimensions are {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"

            # Try to verify image (will raise if corrupted)
            # Note: verify() closes the image, so we do this last
            img.verify()

    except Exception as e:
        logger.warning(
            f"Image verification failed: {str(e)}",
            extra={'filename': sanitize_log_value(file_obj.filename)}
        )
        return False, "Invalid or corrupted image file"

    # =========================================================================
    # VALIDATION PASSED
    # =========================================================================

    logger.info(
        "File validation passed",
        extra={
            'filename': sanitize_log_value(file_obj.filename),
            'extension': ext,
            'size': file_size
        }
    )

    return True, None

@api_bp.route('/v1/encounter-set/unverified', methods=['GET'])
@login_required
@roles_required("admin", "local_admin", "optometrist")
def list_unverified_encounter_sets():
    """List set-based encounters that need verification."""
    with transaction_scope() as db:
        query = select(PatientEncounters).where(
            and_(
                PatientEncounters.is_set_based == True,
                PatientEncounters.encounter_verified_status != "verified"
            )
        ).order_by(PatientEncounters.capture_date.desc())
        
        query = apply_scoping(query, PatientEncounters, current_user, "view")
        encounters = db.execute(query).scalars().all()
        
        return jsonify([{
            "uuid": enc.uuid,
            "patient_id": enc.patient_id,
            "patient_name": enc.name,
            "capture_date": enc.capture_date,
            "image_count": len(enc.encounter_set_images)
        } for enc in encounters])

@api_bp.route('/v1/encounter-set/<uuid>/details', methods=['GET'])
@login_required
@roles_required("admin", "local_admin", "optometrist")
def get_encounter_set_details(uuid):
    """Get details and images for a specific encounter set."""
    with transaction_scope() as db:
        query = select(PatientEncounters).where(PatientEncounters.uuid == uuid).options(
            selectinload(PatientEncounters.encounter_set_images)
        )
        query = apply_scoping(query, PatientEncounters, current_user, "view")
        encounter = db.execute(query).scalar_one_or_none()
        
        if not encounter:
            return jsonify({"error": "Encounter not found"}), 404
            
        images = [{
            "uuid": img.uuid,
            "spatial_position": img.spatial_position,
            "referral_needed_or_positive_image": img.referral_needed_or_positive_image,
            "url": url_for('media.get_encounter_set_image', uuid=img.uuid),
            "thumbnail_url": url_for('media.get_encounter_set_thumbnail', uuid=img.uuid) if img.thumbnail_filename else None
        } for img in encounter.encounter_set_images]
        
        return jsonify({
            "uuid": encounter.uuid,
            "patient_id": encounter.patient_id,
            "patient_name": encounter.name,
            "capture_date": encounter.capture_date,
            "referral_suggestion": encounter.referral_suggestion,
            "referral_positive_diseases": encounter.referral_positive_diseases_json or [],
            "images": images
        })

@api_bp.route('/v1/encounter-set/image/<uuid>/position', methods=['POST'])
@login_required
@roles_required("admin", "local_admin", "optometrist")
def update_image_position(uuid):
    """Update the spatial position of an image."""
    # =========================================================================
    # P0.4: FIX TYPE CONFUSION - Validate null first, then type, then range
    # =========================================================================

    pos_raw = request.json.get("spatial_position")

    # Step 1: Null check
    if pos_raw is None:
        return jsonify({"error": "Missing spatial_position"}), 400

    # Step 2: Type validation (before using int())
    try:
        spatial_position = int(pos_raw)
    except (ValueError, TypeError):
        return jsonify({
            "error": "Invalid spatial_position",
            "message": "Must be an integer between 1 and 9"
        }), 400

    # Step 3: Range validation
    if not (1 <= spatial_position <= 9):
        return jsonify({
            "error": "Invalid spatial_position",
            "message": "Must be between 1 and 9"
        }), 400
        
    with transaction_scope() as db:
        # Check permission via encounter scoping
        query = select(EncounterSetImage).where(EncounterSetImage.uuid == uuid).options(
            selectinload(EncounterSetImage.patient_encounter)
        )
        img = db.execute(query).scalar_one_or_none()

        if not img:
            return jsonify({"error": "Image not found"}), 404

        # Scope check - verify user has access to this encounter
        enc_query = select(PatientEncounters).where(PatientEncounters.id == img.patient_encounter_id)
        enc_query = apply_scoping(enc_query, PatientEncounters, current_user, "edit")
        if not db.execute(enc_query).scalar_one_or_none():
            return jsonify({"error": "Access denied"}), 403

        # Update position (P0.5: Handle race condition via database constraint)
        img.spatial_position = spatial_position

        try:
            db.commit()
        except IntegrityError as e:
            # Unique constraint violation - another request took this position
            if 'uq_encounter_set_image_position' in str(e):
                return jsonify({
                    "error": "Position already occupied",
                    "message": "Another user moved an image to this position. Please try a different position."
                }), 409
            # Other integrity errors should be raised
            raise

        logger.info(
            "Image position updated",
            extra={
                'image_uuid': uuid,
                'new_position': spatial_position,
                'user_id': current_user.id
            }
        )

        return jsonify({"message": "Position updated"})

def generate_mobile_token(hospital_id, lab_unit_id, allowed_diseases):
    """
    Generate a JWT token for mobile upload devices.
    """
    jwt_secret = os.environ.get("JWT_SECRET")
    if not jwt_secret:
        logger.error("JWT_SECRET not configured in environment")
        raise RuntimeError("JWT_SECRET not configured")

    payload = {
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "allowed_diseases": allowed_diseases,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=14) # 14-day mobile device token
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

@api_bp.route('/v1/encounter-set/upload', methods=['POST'])
@api_rate_limit("60 per minute")
@token_auth_required
def upload_encounter_set_image():
    """
    Upload a single image for an encounter set.
    """
    claims = request.mobile_claims
    mobile_auth = getattr(request, "mobile_auth", {})
    uploader_user_id = mobile_auth.get("user_id")
    try:
        lab_unit_id = int(claims.get("lab_unit_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Upload token is missing lab_unit_id"}), 403
    profile_id_raw = request.form.get("upload_profile_id") or request.form.get("profile_id")
    project_id_raw = request.form.get("project_id")
    disease_id_raw = request.form.get("disease_id")
    camera_id_raw = request.form.get("camera_id")
    area_id_raw = request.form.get("area_id")
    try:
        upload_profile_id = int(profile_id_raw) if profile_id_raw else None
        project_id = int(project_id_raw) if project_id_raw else None
        disease_id = int(disease_id_raw) if disease_id_raw else None
        camera_id = int(camera_id_raw) if camera_id_raw else None
        area_id = int(area_id_raw) if area_id_raw else None
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid upload_profile_id, project_id, disease_id, camera_id, or area_id"}), 400
    is_mydriatic = (request.form.get("is_mydriatic") or "").strip().lower() in {"1", "true", "yes", "on"}
    referral_suggestion_raw = request.form.get("referral_suggestion")
    referral_suggestion = normalize_referral_suggestion(referral_suggestion_raw)
    referral_positive_diseases_raw = request.form.getlist("referral_positive_diseases")
    if not referral_positive_diseases_raw:
        referral_positive_diseases_raw = request.form.getlist("referral_positive_disease")
    if not referral_positive_diseases_raw and request.form.get("referral_positive_diseases"):
        referral_positive_diseases_raw = [request.form.get("referral_positive_diseases")]
    referral_positive_diseases = normalize_referral_positive_diseases(referral_positive_diseases_raw)
    image_referral_raw = request.form.get("referral_needed_or_positive_image")
    if image_referral_raw is None:
        image_referral_raw = request.form.get("refrralneed_or_positive_image")
    image_referral_suggestion = normalize_referral_suggestion(image_referral_raw)

    if not uploader_user_id:
        return jsonify({"error": "Upload token is not associated with a user"}), 403
    if not upload_profile_id:
        return jsonify({"error": "Missing upload_profile_id"}), 400
    if not camera_id or not area_id:
        return jsonify({"error": "Missing camera_id or area_id"}), 400
    
    # Validate spatial position
    spatial_pos_raw = request.form.get("spatial_position")
    if not spatial_pos_raw or not spatial_pos_raw.isdigit():
        return jsonify({"error": "Missing or invalid spatial_position"}), 400
    
    spatial_pos = int(spatial_pos_raw)
    if not (1 <= spatial_pos <= 9):
        return jsonify({"error": "spatial_position must be between 1 and 9"}), 400
        
    # Check for file
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # =========================================================================
    # VALIDATE FILE (size, extension, magic bytes, MIME type, content)
    # =========================================================================
    is_valid, error_msg = validate_image_file(file)
    if not is_valid:
        # P1.2: Return 413 Payload Too Large for file size errors
        if "exceeds maximum limit" in error_msg or "size" in error_msg.lower():
            return jsonify({"error": "File too large", "message": error_msg}), 413
        return jsonify({"error": "Invalid image file", "message": error_msg}), 400

    encounter_uuid = request.form.get("encounter_uuid")
    
    with transaction_scope() as db:
        uploader_user = db.execute(
            select(User).where(User.id == uploader_user_id).options(selectinload(User.roles))
        ).scalar_one_or_none()
        if uploader_user is None or not uploader_user.has_role("fileUploader"):
            return jsonify({"error": "Forbidden", "message": "Encounter set uploads require the fileUploader role"}), 403

        try:
            upload_profile = validate_profile_upload_scope(
                db,
                uploader_user_id,
                profile_id=upload_profile_id,
                upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
                project_id=project_id,
                lab_unit_id=lab_unit_id,
                disease_id=disease_id,
                camera_id=camera_id,
                area_id=area_id,
                is_mydriatic=is_mydriatic,
            )
        except UploadProfileError as exc:
            return jsonify({"error": exc.code, "message": exc.message}), 403
        if upload_profile.lab_unit_id != lab_unit_id:
            return jsonify({"error": "profile_lab_mismatch", "message": "Upload profile is not valid for this token lab unit."}), 403
        target_disease_ids = [disease_id] if disease_id else sorted(encounter_set_grading_scheme_ids(upload_profile))

        if encounter_uuid:
            encounter = db.query(PatientEncounters).filter_by(uuid=encounter_uuid).first()
            if not encounter:
                return jsonify({"error": "Encounter not found"}), 404
            
            # Security check: Ensure encounter belongs to the same lab unit as token
            if encounter.lab_unit_id != lab_unit_id:
                logger.warning("Cross-lab upload attempt. Encounter: %s, Token Lab: %s", 
                               sanitize_log_value(encounter.id), sanitize_log_value(lab_unit_id))
                return jsonify({"error": "Unauthorized access to this encounter"}), 403
            if encounter.project_id and encounter.project_id != upload_profile.project_id:
                return jsonify({"error": "Encounter belongs to a different project"}), 403
            if encounter.project_id is None:
                encounter.project_id = upload_profile.project_id
            if encounter.upload_profile_id and encounter.upload_profile_id != upload_profile.profile_id:
                return jsonify({"error": "Encounter belongs to a different upload profile"}), 403
            if encounter.upload_profile_id is None:
                encounter.upload_profile_id = upload_profile.profile_id
            if encounter.disease_id is None:
                encounter.disease_id = target_disease_ids[0] if len(target_disease_ids) == 1 else None
            if referral_positive_diseases_raw:
                encounter.referral_positive_diseases_json = referral_positive_diseases
        else:
            # Create new encounter
            patient_id = request.form.get("patient_id")
            patient_name = request.form.get("patient_name")
            capture_date = request.form.get("capture_date") or utcnow().strftime("%Y-%m-%d")
            
            if not patient_id or not patient_name:
                return jsonify({"error": "Missing patient_id or patient_name for new encounter"}), 400
            
            encounter = PatientEncounters(
                name=patient_name,
                patient_id=patient_id,
                capture_date=capture_date,
                lab_unit_id=lab_unit_id,
                project_id=upload_profile.project_id,
                upload_profile_id=upload_profile.profile_id,
                disease_id=target_disease_ids[0] if len(target_disease_ids) == 1 else None,
                is_set_based=True,
                referral_suggestion=referral_suggestion,
                referral_suggestion_updated_at=utcnow() if referral_suggestion_raw is not None else None,
                referral_positive_diseases_json=referral_positive_diseases,
                uuid=str(uuid4())
            )
            db.add(encounter)
            db.flush() # Get encounter.id
            encounter_uuid = encounter.uuid

        existing_targets = {
            row[0]
            for row in db.execute(
                select(PatientEncounterTargetDisease.disease_id).where(
                    PatientEncounterTargetDisease.patient_encounter_id == encounter.id
                )
            ).all()
        }
        if existing_targets and existing_targets != set(target_disease_ids):
            return jsonify({"error": "Encounter target diseases cannot be changed after upload starts"}), 403
        for target_disease_id in target_disease_ids:
            if target_disease_id not in existing_targets:
                db.add(
                    PatientEncounterTargetDisease(
                        patient_encounter_id=encounter.id,
                        disease_id=target_disease_id,
                        is_default=False,
                    )
                )
            
        # =========================================================================
        # HANDLE FILE STORAGE - USE SAFE FILENAMES
        # =========================================================================

        # Generate UUID for file (not user-provided filename)
        img_uuid = str(uuid4())

        # Force all images to .jpg to prevent execution (even if uploaded as .png, store as .jpg)
        # This prevents security issues if file ends up in wrong directory
        safe_filename = f"{img_uuid}.jpg"

        # Directory structure: files/encounter_sets/YYYY_MM_DD/encounter_id/
        date_str = utcnow().strftime("%Y_%m_%d")
        folder_rel = f"files/encounter_sets/{date_str}/{encounter.id}"
        save_path = os.path.join(current_app.root_path, folder_rel)

        # Verify path is within base directory (prevent path traversal)
        real_path = os.path.realpath(save_path)
        base_path = os.path.realpath(current_app.root_path)
        if not real_path.startswith(base_path):
            logger.error(f"Path traversal attempt detected: {real_path}")
            return jsonify({"error": "Invalid storage path"}), 500

        os.makedirs(save_path, exist_ok=True)

        # Save with safe filename (not user-provided)
        file_path = os.path.join(save_path, safe_filename)
        file.save(file_path)

        logger.info(
            "Image saved successfully",
            extra={
                'image_uuid': img_uuid,
                'encounter_uuid': sanitize_log_value(encounter_uuid),
                'original_filename': sanitize_log_value(file.filename),
                'stored_filename': safe_filename,
                'size': os.path.getsize(file_path)
            }
        )

        # Create EncounterSetImage record
        # Store ORIGINAL filename separately for reference (not for serving)
        set_image = EncounterSetImage(
            uuid=img_uuid,
            patient_encounter_id=encounter.id,
            spatial_position=spatial_pos,
            original_filename=file.filename,  # User's original name for reference only
            folder_rel=folder_rel,
            project_id=upload_profile.project_id,
            hospital_id=upload_profile.hospital_id,
            camera_id=camera_id,
            area_id=area_id,
            is_mydriatic=is_mydriatic,
            referral_needed_or_positive_image=image_referral_suggestion,
            referral_needed_or_positive_image_updated_at=utcnow() if image_referral_raw is not None else None,
            created_at=utcnow()
        )
        db.add(set_image)
        db.commit()

        try:
            enqueue_wadhwani_for_encounter_ids(
                [encounter.id],
                trigger_timing="on_image_received",
                user_id=uploader_user_id,
                username=getattr(uploader_user, "username", None),
                remote_addr=request.remote_addr,
            )
        except Exception as exc:
            current_app.logger.warning(
                "Failed to queue EncounterSet Wadhwani inference after image upload encounter_id=%s error=%s",
                sanitize_log_value(encounter.id),
                sanitize_log_value(exc),
                exc_info=True,
            )

        # Schedule thumbnail generation in background
        try:
            from utils.thumbnail_jobs import schedule_encounter_set_thumbnails
            schedule_encounter_set_thumbnails(
                [set_image.id],
                current_app,
                user_context={
                    'user_id': current_user.id,
                    'username': current_user.username,
                    'ip': request.remote_addr
                }
            )
        except Exception as e:
            # Log but don't fail the upload if thumbnail scheduling fails
            current_app.logger.error(
                "Failed to schedule thumbnail generation for encounter set image %s: %s",
                set_image.uuid,
                e
            )
        
        return jsonify({
            "message": "Image uploaded successfully",
            "encounter_id": encounter.id,
            "encounter_uuid": encounter_uuid,
            "image_uuid": img_uuid,
            "spatial_position": spatial_pos,
            "referral_suggestion": encounter.referral_suggestion,
            "referral_positive_diseases": encounter.referral_positive_diseases_json or [],
            "referral_needed_or_positive_image": set_image.referral_needed_or_positive_image,
        }), 201
