import os
import logging
import jwt
from datetime import datetime, timedelta, timezone
from flask import jsonify, request, current_app, url_for
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
from authz import RecordColumns, access_context, role_scoped_rows
from upload_profiles.service import (
    UPLOAD_KIND_ENCOUNTER_SET,
    UploadProfileError,
    encounter_set_grading_scheme_ids,
    validate_profile_upload_scope,
)
from encounter_sets.monocular_status import update_monocular_status


@api_bp.route("/encounter-sets/<uuid>/monocular-status", methods=["PATCH"])
@login_required
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
        
        query = role_scoped_rows(
            query,
            access_context(db, current_user),
            RecordColumns(
                project_id=PatientEncounters.project_id,
                lab_unit_id=PatientEncounters.lab_unit_id,
            ),
            lab_roles={"local_admin", "optometrist"},
            hospital_roles={"local_admin"},
            project_roles={"project_pi", "site_pi", "project_admin", "optometrist", "verifier"},
            allow_admin=True,
        )
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
        query = role_scoped_rows(
            query,
            access_context(db, current_user),
            RecordColumns(
                project_id=PatientEncounters.project_id,
                lab_unit_id=PatientEncounters.lab_unit_id,
            ),
            lab_roles={"local_admin", "optometrist"},
            hospital_roles={"local_admin"},
            project_roles={"project_pi", "site_pi", "project_admin", "optometrist", "verifier"},
            allow_admin=True,
        )
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
        enc_query = role_scoped_rows(
            enc_query,
            access_context(db, current_user),
            RecordColumns(
                project_id=PatientEncounters.project_id,
                lab_unit_id=PatientEncounters.lab_unit_id,
            ),
            lab_roles={"local_admin", "optometrist"},
            hospital_roles={"local_admin"},
            project_roles={"project_admin", "optometrist", "verifier"},
            allow_admin=True,
        )
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
