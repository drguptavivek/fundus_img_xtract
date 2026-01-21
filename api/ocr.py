from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from flask import jsonify, request
from flask_login import current_user

from app_cache import cache
from auth.roles import roles_required
from models import DirectImageUpload, EncounterFile, IMAGE_DIR, PatientEncounters, ZipFile
from utils.fileUtils import abs_from_parts
from utils.hospital_scoping import apply_scoping, determine_scoping_context
from utils.log_sanitize import sanitize_log_value
from utils.media_cache import get_media_cache_version
from utils.ocr_pii import detect_pii_for_path
from utils.utils import with_session

from . import api_bp


_OCR_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30


def _resolve_image_path(image_uuid: str) -> Optional[str]:
    context = determine_scoping_context()
    with with_session() as db:
        encounter_query = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid == image_uuid)
        )
        encounter_query = apply_scoping(encounter_query, PatientEncounters, current_user, context)
        encounter_result = encounter_query.first()

        direct_query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == image_uuid)
        direct_query = apply_scoping(direct_query, DirectImageUpload, current_user, context)
        direct_image = direct_query.first()

        if encounter_result and direct_image:
            return None

        if encounter_result:
            encounter_file, patient_encounter, zip_file = encounter_result
            if not encounter_file or not encounter_file.filename:
                return None
            upload_date = zip_file.upload_date if zip_file else None
            if not upload_date:
                return None
            upload_date_str = upload_date.strftime("%Y_%m_%d")
            return str(IMAGE_DIR / upload_date_str / encounter_file.filename)

        if direct_image:
            if not direct_image.filename:
                return None
            filename = direct_image.edited_filename or direct_image.filename
            kind = "edited" if direct_image.edited_filename else "orig"
            try:
                return str(abs_from_parts(direct_image.folder_rel, filename, kind))
            except (OSError, ValueError):
                return None

    return None


@api_bp.route("/ocr/pii/<string:image_uuid>", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "data_exporter",
    "dataset_creator",
    "analytics_viewer",
    "fileUploader",
    "optometrist",
    "ophthalmologist",
    "resident",
)
def api_ocr_pii(image_uuid: str):
    start = time.perf_counter()
    force_refresh = request.args.get("refresh", "0") in {"1", "true", "yes"}
    cache_version = get_media_cache_version(image_uuid)
    cache_key = f"ocr:pii:{image_uuid}:{cache_version}"
    cached = cache.get(cache_key) if not force_refresh else None
    if isinstance(cached, dict) and not force_refresh:
        duration_ms = int((time.perf_counter() - start) * 1000)
        cached = {**cached, "duration_ms": duration_ms}
        return jsonify({"success": True, "data": cached, "cached": True})

    image_path = _resolve_image_path(image_uuid)
    if not image_path:
        return jsonify({"success": False, "error": "Image not found"}), 404

    try:
        ocr_result = detect_pii_for_path(image_path)
        status = "detected" if ocr_result.get("is_pii") else "clear"
        duration_ms = int((time.perf_counter() - start) * 1000)
        result: Dict[str, Any] = {
            "status": status,
            "label": "PII detected" if status == "detected" else "No PII detected",
            "valid_detections": ocr_result.get("valid_detections", 0),
            "pattern_matches": ocr_result.get("pattern_matches", 0),
            "version": cache_version,
            "duration_ms": duration_ms,
        }
        cache.set(cache_key, result, timeout=_OCR_CACHE_TTL_SECONDS)
        return jsonify({"success": True, "data": result, "cached": False})
    except Exception as exc:
        logger = logging.getLogger("ocr_pii")
        logger.warning(
            "PII OCR failed for image_uuid=%s: %s",
            sanitize_log_value(image_uuid),
            sanitize_log_value(str(exc)),
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        result = {
            "status": "error",
            "label": "OCR unavailable",
            "version": cache_version,
            "duration_ms": duration_ms,
        }
        cache.set(cache_key, result, timeout=_OCR_CACHE_TTL_SECONDS)
        return jsonify({"success": True, "data": result, "cached": False})
