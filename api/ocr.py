from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from flask import jsonify, request
from flask_login import current_user

from app_cache import cache
from auth.roles import roles_required
from models import DirectImageUpload, EncounterFile, IMAGE_DIR, ImagePiiVerification, PatientEncounters, ZipFile
from utils.fileUtils import abs_from_parts
from utils.hospital_scoping import apply_scoping, determine_scoping_context
from utils.log_sanitize import sanitize_log_value
from utils.media_cache import get_media_cache_version
from utils.ocr_pii import detect_pii_details_for_path
from auth.utils import utcnow
from utils.utils import with_session

from . import api_bp


_OCR_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30


def _resolve_image_variant_map(image_uuids: Iterable[str]) -> Dict[str, Optional[str]]:
    uuids = [uuid for uuid in image_uuids if uuid]
    if not uuids:
        return {}

    context = determine_scoping_context()
    with with_session() as db:
        encounter_query = (
            db.query(EncounterFile.uuid)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid.in_(uuids))
        )
        encounter_query = apply_scoping(encounter_query, PatientEncounters, current_user, context)
        encounter_uuids = {row[0] for row in encounter_query.all()}

        direct_query = (
            db.query(DirectImageUpload.uuid, DirectImageUpload.edited_filename)
            .filter(DirectImageUpload.uuid.in_(uuids))
        )
        direct_query = apply_scoping(direct_query, DirectImageUpload, current_user, context)
        direct_variants = {
            uuid: ("edited" if edited_filename else "orig")
            for uuid, edited_filename in direct_query.all()
        }

    variant_map: Dict[str, Optional[str]] = {}
    for uuid in uuids:
        if uuid in direct_variants:
            variant_map[uuid] = direct_variants[uuid]
        elif uuid in encounter_uuids:
            variant_map[uuid] = "orig"
        else:
            variant_map[uuid] = None
    return variant_map


def _resolve_image_path(image_uuid: str) -> tuple[Optional[str], Optional[str]]:
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
            return None, None

        if encounter_result:
            encounter_file, patient_encounter, zip_file = encounter_result
            if not encounter_file or not encounter_file.filename:
                return None, None
            upload_date = zip_file.upload_date if zip_file else None
            if not upload_date:
                return None, None
            upload_date_str = upload_date.strftime("%Y_%m_%d")
            return str(IMAGE_DIR / upload_date_str / encounter_file.filename), "orig"

        if direct_image:
            if not direct_image.filename:
                return None, None
            filename = direct_image.edited_filename or direct_image.filename
            kind = "edited" if direct_image.edited_filename else "orig"
            try:
                return str(abs_from_parts(direct_image.folder_rel, filename, kind)), kind
            except (OSError, ValueError):
                return None, None

    return None, None


def _record_pii_verification(
    image_uuid: str,
    image_variant: str,
    status: str,
    checked_at: datetime,
    source: str = "auto",
    detections: list[dict[str, Any]] | None = None,
    roi: dict[str, Any] | None = None,
) -> None:
    try:
        with with_session() as db:
            existing = (
                db.query(ImagePiiVerification)
                .filter(
                    ImagePiiVerification.image_uuid == image_uuid,
                    ImagePiiVerification.image_variant == image_variant,
                )
                .first()
            )
            if existing:
                existing.pii_status = status
                existing.checked_at = checked_at
                existing.source = source
                if detections is not None:
                    existing.detections_json = json.dumps(detections)
                if roi is not None:
                    existing.roi_json = json.dumps(roi)
            else:
                db.add(
                    ImagePiiVerification(
                        image_uuid=image_uuid,
                        image_variant=image_variant,
                        pii_status=status,
                        checked_at=checked_at,
                        source=source,
                        detections_json=json.dumps(detections) if detections is not None else None,
                        roi_json=json.dumps(roi) if roi is not None else None,
                    )
                )
    except Exception as exc:
        logger = logging.getLogger("ocr_pii")
        logger.warning(
            "PII OCR DB update failed for image_uuid=%s: %s",
            sanitize_log_value(image_uuid),
            sanitize_log_value(str(exc)),
        )


@api_bp.route("/ocr/pii/batch", methods=["POST"])
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
def api_ocr_pii_batch():
    payload = request.get_json(silent=True) or {}
    image_uuids = payload.get("image_uuids")
    if not isinstance(image_uuids, list):
        return jsonify({"success": False, "error": "image_uuids must be a list"}), 400
    image_uuids = [uuid for uuid in image_uuids if isinstance(uuid, str) and uuid]
    if not image_uuids:
        return jsonify({"success": True, "data": {}})

    variant_map = _resolve_image_variant_map(image_uuids)
    with with_session() as db:
        records = (
            db.query(
                ImagePiiVerification.image_uuid,
                ImagePiiVerification.image_variant,
                ImagePiiVerification.pii_status,
                ImagePiiVerification.checked_at,
                ImagePiiVerification.source,
            )
            .filter(ImagePiiVerification.image_uuid.in_(image_uuids))
            .all()
        )
    record_map = {(rec.image_uuid, rec.image_variant): rec for rec in records}

    response_data: Dict[str, Dict[str, Any]] = {}
    for uuid in image_uuids:
        variant = variant_map.get(uuid)
        if not variant:
            response_data[uuid] = {
                "status": "error",
                "label": "Image not found",
                "variant": None,
            }
            continue
        record = record_map.get((uuid, variant))
        if not record:
            response_data[uuid] = {
                "status": "pending",
                "label": "Pending",
                "variant": variant,
            }
            continue
        response_data[uuid] = {
            "status": record.pii_status,
            "label": "PII detected" if record.pii_status == "detected" else "No PII detected",
            "variant": variant,
            "checked_at": record.checked_at.isoformat(),
            "source": record.source,
        }

    return jsonify({"success": True, "data": response_data})


@api_bp.route("/ocr/pii/boxes/<string:image_uuid>", methods=["GET"])
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
def api_ocr_pii_boxes(image_uuid: str):
    start = time.perf_counter()
    image_path, image_variant = _resolve_image_path(image_uuid)
    if not image_path or not image_variant:
        return jsonify({"success": False, "error": "Image not found"}), 404

    try:
        with with_session() as db:
            existing = (
                db.query(
                    ImagePiiVerification.pii_status,
                    ImagePiiVerification.detections_json,
                    ImagePiiVerification.roi_json,
                    ImagePiiVerification.source,
                )
                .filter(
                    ImagePiiVerification.image_uuid == image_uuid,
                    ImagePiiVerification.image_variant == image_variant,
                )
                .first()
            )
        if existing and existing.detections_json:
            detections = json.loads(existing.detections_json)
            roi = json.loads(existing.roi_json) if existing.roi_json else None
            duration_ms = int((time.perf_counter() - start) * 1000)
            return jsonify({
                "success": True,
                "data": {
                    "status": existing.pii_status,
                    "label": "PII detected" if existing.pii_status == "detected" else "No PII detected",
                    "valid_detections": len(detections),
                    "pattern_matches": len([d for d in detections if d.get("matches_pattern")]),
                    "detections": detections,
                    "roi": roi,
                    "duration_ms": duration_ms,
                    "source": existing.source,
                },
            })

        if existing and existing.source == "manual":
            duration_ms = int((time.perf_counter() - start) * 1000)
            return jsonify({
                "success": True,
                "data": {
                    "status": existing.pii_status,
                    "label": "PII detected" if existing.pii_status == "detected" else "No PII detected",
                    "valid_detections": 0,
                    "pattern_matches": 0,
                    "detections": [],
                    "roi": None,
                    "duration_ms": duration_ms,
                    "source": "manual",
                },
            })

        ocr_result = detect_pii_details_for_path(image_path)
        status = "detected" if ocr_result.get("is_pii") else "clear"
        duration_ms = int((time.perf_counter() - start) * 1000)
        checked_at = utcnow()
        _record_pii_verification(
            image_uuid,
            image_variant,
            status,
            checked_at,
            source="auto",
            detections=ocr_result.get("detections"),
            roi=ocr_result.get("roi"),
        )
        result: Dict[str, Any] = {
            "status": status,
            "label": "PII detected" if status == "detected" else "No PII detected",
            "valid_detections": ocr_result.get("valid_detections", 0),
            "pattern_matches": ocr_result.get("pattern_matches", 0),
            "detections": ocr_result.get("detections", []),
            "roi": ocr_result.get("roi"),
            "duration_ms": duration_ms,
            "source": "auto",
        }
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        logger = logging.getLogger("ocr_pii")
        logger.warning(
            "PII OCR box failed for image_uuid=%s: %s",
            sanitize_log_value(image_uuid),
            sanitize_log_value(str(exc)),
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        result = {
            "status": "error",
            "label": "OCR unavailable",
            "duration_ms": duration_ms,
        }
        return jsonify({"success": True, "data": result})


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
    if not force_refresh:
        with with_session() as db:
            manual = (
                db.query(ImagePiiVerification.pii_status)
                .filter(
                    ImagePiiVerification.image_uuid == image_uuid,
                    ImagePiiVerification.source == "manual",
                )
                .first()
            )
        if manual:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return jsonify({
                "success": True,
                "data": {
                    "status": manual.pii_status,
                    "label": "PII detected" if manual.pii_status == "detected" else "No PII detected",
                    "valid_detections": 0,
                    "pattern_matches": 0,
                    "version": cache_version,
                    "duration_ms": duration_ms,
                    "source": "manual",
                },
                "cached": False,
            })
    cached = cache.get(cache_key) if not force_refresh else None
    if isinstance(cached, dict) and not force_refresh:
        duration_ms = int((time.perf_counter() - start) * 1000)
        cached = {**cached, "duration_ms": duration_ms}
        return jsonify({"success": True, "data": cached, "cached": True})

    image_path, image_variant = _resolve_image_path(image_uuid)
    if not image_path or not image_variant:
        return jsonify({"success": False, "error": "Image not found"}), 404

    try:
        ocr_result = detect_pii_details_for_path(image_path)
        status = "detected" if ocr_result.get("is_pii") else "clear"
        duration_ms = int((time.perf_counter() - start) * 1000)
        checked_at = utcnow()
        _record_pii_verification(
            image_uuid,
            image_variant,
            status,
            checked_at,
            source="auto",
            detections=ocr_result.get("detections"),
            roi=ocr_result.get("roi"),
        )
        result: Dict[str, Any] = {
            "status": status,
            "label": "PII detected" if status == "detected" else "No PII detected",
            "valid_detections": ocr_result.get("valid_detections", 0),
            "pattern_matches": ocr_result.get("pattern_matches", 0),
            "version": cache_version,
            "duration_ms": duration_ms,
            "source": "auto",
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
        checked_at = utcnow()
        if image_variant:
            _record_pii_verification(image_uuid, image_variant, "error", checked_at, source="auto")
        result = {
            "status": "error",
            "label": "OCR unavailable",
            "version": cache_version,
            "duration_ms": duration_ms,
            "source": "auto",
        }
        cache.set(cache_key, result, timeout=_OCR_CACHE_TTL_SECONDS)
        return jsonify({"success": True, "data": result, "cached": False})
