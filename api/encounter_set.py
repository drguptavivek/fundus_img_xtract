import os
import logging
import jwt
from datetime import datetime, timedelta, timezone
from flask import jsonify, request, current_app
from uuid import uuid4
from functools import wraps

from . import api_bp
from db_transaction_manager import transaction_scope
from models import PatientEncounters, EncounterSetImage
from auth.utils import utcnow
from auth.decorators import token_auth_required
from utils.rate_limiter import api_rate_limit
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("api.encounter_set")

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
    lab_unit_id = claims.get("lab_unit_id")
    
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

    encounter_uuid = request.form.get("encounter_uuid")
    
    with transaction_scope() as db:
        if encounter_uuid:
            encounter = db.query(PatientEncounters).filter_by(uuid=encounter_uuid).first()
            if not encounter:
                return jsonify({"error": "Encounter not found"}), 404
            
            # Security check: Ensure encounter belongs to the same lab unit as token
            if encounter.lab_unit_id != lab_unit_id:
                logger.warning("Cross-lab upload attempt. Encounter: %s, Token Lab: %s", 
                               sanitize_log_value(encounter.id), sanitize_log_value(lab_unit_id))
                return jsonify({"error": "Unauthorized access to this encounter"}), 403
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
                is_set_based=True,
                uuid=str(uuid4())
            )
            db.add(encounter)
            db.flush() # Get encounter.id
            encounter_uuid = encounter.uuid
            
        # Handle file storage
        ext = os.path.splitext(file.filename)[1]
        img_uuid = str(uuid4())
        filename = f"{img_uuid}{ext}"
        
        # Directory structure: files/encounter_sets/YYYY_MM_DD/encounter_id/
        date_str = utcnow().strftime("%Y_%m_%d")
        folder_rel = f"files/encounter_sets/{date_str}/{encounter.id}"
        save_path = os.path.join(current_app.root_path, folder_rel)
        os.makedirs(save_path, exist_ok=True)
        
        file.save(os.path.join(save_path, filename))
        
        # Create EncounterSetImage record
        set_image = EncounterSetImage(
            uuid=img_uuid,
            patient_encounter_id=encounter.id,
            spatial_position=spatial_pos,
            original_filename=filename,
            folder_rel=folder_rel,
            created_at=utcnow()
        )
        db.add(set_image)
        db.commit()
        
        return jsonify({
            "message": "Image uploaded successfully",
            "encounter_id": encounter.id,
            "encounter_uuid": encounter_uuid,
            "image_uuid": img_uuid,
            "spatial_position": spatial_pos
        }), 201