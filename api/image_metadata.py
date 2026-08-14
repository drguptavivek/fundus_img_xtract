from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from flask import jsonify, request
from flask_login import current_user, login_required

from app_cache import cache
from db_transaction_manager import get_db_session
from models import BASE_DIR, DirectImageUpload, EncounterFile, EncounterSetImage, IMAGE_DIR, ImageMetadata, PatientEncounters, ZipFile
from utils.fileUtils import abs_from_parts
from utils.image_metadata import extract_image_metadata, upsert_image_metadata
from utils.log_sanitize import sanitize_log_value

from . import api_bp
from media.authorization import (
    IMAGE_SOURCE_TYPES,
    MediaAccessDenied,
    MediaResolutionError,
    authorize_media_source,
)

_LOGGER = logging.getLogger("image_metadata_api")
_METADATA_CACHE_TTL_SECONDS = 10 * 60


def _serialize_metadata(meta: ImageMetadata, include_raw: bool) -> dict:
    payload = {
        "image_uuid": meta.image_uuid,
        "image_variant": meta.image_variant,
        "width": meta.width,
        "height": meta.height,
        "format": meta.format,
        "mode": meta.mode,
        "bit_depth": meta.bit_depth,
        "is_grayscale": meta.is_grayscale,
        "has_alpha": meta.has_alpha,
        "file_size_bytes": meta.file_size_bytes,
        "dpi_x": meta.dpi_x,
        "dpi_y": meta.dpi_y,
        "avg_luminance": meta.avg_luminance,
        "max_luminance": meta.max_luminance,
        "luminance_std": meta.luminance_std,
        "mean_r": meta.mean_r,
        "mean_g": meta.mean_g,
        "mean_b": meta.mean_b,
        "median_r": meta.median_r,
        "median_g": meta.median_g,
        "median_b": meta.median_b,
        "exif_present": bool(meta.exif_json),
        "iptc_present": bool(meta.iptc_json),
        "size_ok": bool(meta.width and meta.height and meta.width >= 1024 and meta.height >= 768),
        "created_at": meta.created_at.isoformat() + "Z" if meta.created_at else None,
        "updated_at": meta.updated_at.isoformat() + "Z" if meta.updated_at else None,
    }
    if include_raw:
        payload.update(
            {
                "histogram_json": meta.histogram_json,
                "exif_json": meta.exif_json,
                "iptc_json": meta.iptc_json,
            }
        )
    return payload


def _metadata_int(metadata: dict | None, *keys: str) -> int | None:
    if not metadata:
        return None
    for key in keys:
        value = metadata.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _serialize_encounter_set_image_fallback(image: EncounterSetImage, variant: str) -> dict:
    metadata = image.metadata_json or {}
    width = _metadata_int(metadata, "width", "width_px", "image_width")
    height = _metadata_int(metadata, "height", "height_px", "image_height")
    return {
        "image_uuid": image.uuid,
        "image_variant": variant,
        "width": width,
        "height": height,
        "format": None,
        "mode": None,
        "bit_depth": None,
        "is_grayscale": None,
        "has_alpha": None,
        "file_size_bytes": None,
        "dpi_x": None,
        "dpi_y": None,
        "avg_luminance": None,
        "max_luminance": None,
        "luminance_std": None,
        "mean_r": None,
        "mean_g": None,
        "mean_b": None,
        "median_r": None,
        "median_g": None,
        "median_b": None,
        "exif_present": False,
        "iptc_present": False,
        "size_ok": bool(width and height and width >= 1024 and height >= 768) if width and height else None,
        "created_at": image.created_at.isoformat() + "Z" if image.created_at else None,
        "updated_at": None,
    }


def _resolve_image_info(
    db,
    image_uuid: str,
    variant: Optional[str] = None,
    *,
    action: str = "media.metadata.read",
) -> tuple[Optional[str], Optional[str], Optional[int], Optional[int], Optional[EncounterSetImage]]:
    try:
        authorize_media_source(
            db,
            user=current_user,
            media_uuid=image_uuid,
            action=action,
            expected_sources=IMAGE_SOURCE_TYPES,
        )
    except (MediaAccessDenied, MediaResolutionError):
        return None, None, None, None, None
    encounter_query = (
        db.query(EncounterFile, PatientEncounters, ZipFile)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .filter(EncounterFile.uuid == image_uuid)
    )
    encounter_result = encounter_query.first()

    direct_query = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == image_uuid)
    direct_image = direct_query.first()

    encounter_set_query = (
        db.query(EncounterSetImage)
        .join(PatientEncounters, EncounterSetImage.patient_encounter_id == PatientEncounters.id)
        .filter(EncounterSetImage.uuid == image_uuid)
    )
    encounter_set_image = encounter_set_query.first()

    if sum(1 for result in (encounter_result, direct_image, encounter_set_image) if result) > 1:
        return None, None, None, None, None

    if encounter_result:
        encounter_file, patient_encounter, zip_file = encounter_result
        if not encounter_file or not encounter_file.filename:
            return None, None, None, None, None
        upload_date = zip_file.upload_date if zip_file else None
        if not upload_date:
            return None, None, None, None, None
        upload_date_str = upload_date.strftime("%Y_%m_%d")
        path = str(IMAGE_DIR / upload_date_str / encounter_file.filename)
        return path, "orig", encounter_file.id, None, None

    if direct_image:
        if not direct_image.filename:
            return None, None, None, None, None
        requested_variant = variant if variant in {"orig", "edited"} else None
        if requested_variant == "edited" and not direct_image.edited_filename:
            return None, None, None, None, None
        if requested_variant == "orig":
            filename = direct_image.filename
            kind = "orig"
        else:
            filename = direct_image.edited_filename or direct_image.filename
            kind = "edited" if direct_image.edited_filename else "orig"
        try:
            return str(abs_from_parts(direct_image.folder_rel, filename, kind)), kind, None, direct_image.id, None
        except (OSError, ValueError):
            return None, None, None, None, None

    if encounter_set_image:
        requested_variant = variant if variant in {"orig", "edited"} else None
        if requested_variant == "edited" and not encounter_set_image.edited_filename:
            return None, None, None, None, None
        if requested_variant == "edited":
            filename = encounter_set_image.edited_filename
            kind = "edited"
        else:
            filename = encounter_set_image.original_filename
            kind = "orig"
        if not filename:
            return None, None, None, None, None
        return str(BASE_DIR / encounter_set_image.folder_rel / filename), kind, None, None, encounter_set_image

    return None, None, None, None, None


def _cache_key(image_uuid: str, variant: str, include_raw: bool) -> str:
    return f"image-metadata:{image_uuid}:{variant}:{'raw' if include_raw else 'summary'}"


@api_bp.route("/image-metadata/<string:image_uuid>", methods=["GET"])
@login_required
def get_image_metadata(image_uuid: str):
    variant = request.args.get("variant")
    include_raw = request.args.get("include_raw", "0") in {"1", "true", "yes"}

    with get_db_session() as db:
        image_path, resolved_variant, _, _, encounter_set_image = _resolve_image_info(db, image_uuid, variant)
        if not image_path or not resolved_variant:
            return jsonify({"success": False, "error": "Image not found"}), 404
        cache_key = _cache_key(image_uuid, resolved_variant, include_raw)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return jsonify({"success": True, "data": cached, "cached": True})

        meta = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == image_uuid,
                ImageMetadata.image_variant == resolved_variant,
            )
            .first()
        )
        if not meta:
            if encounter_set_image:
                payload = _serialize_encounter_set_image_fallback(encounter_set_image, resolved_variant)
                cache.set(cache_key, payload, timeout=_METADATA_CACHE_TTL_SECONDS)
                return jsonify({"success": True, "data": payload, "cached": False, "fallback": True})
            return jsonify({"success": False, "error": "Metadata not found"}), 404
        payload = _serialize_metadata(meta, include_raw)

    cache.set(cache_key, payload, timeout=_METADATA_CACHE_TTL_SECONDS)
    return jsonify({"success": True, "data": payload, "cached": False})


@api_bp.route("/image-metadata/<string:image_uuid>", methods=["POST"])
@login_required
def extract_image_metadata_api(image_uuid: str):
    payload = request.get_json(silent=True) or {}
    variant = payload.get("variant")
    include_raw = payload.get("include_raw", False) in {True, "true", "1", "yes"}
    force = payload.get("force", False) in {True, "true", "1", "yes"}

    with get_db_session() as db:
        image_path, resolved_variant, encounter_id, direct_id, _ = _resolve_image_info(
            db, image_uuid, variant, action="media.metadata.process"
        )
        if not image_path or not resolved_variant:
            return jsonify({"success": False, "error": "Image not found"}), 404

        meta = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == image_uuid,
                ImageMetadata.image_variant == resolved_variant,
            )
            .first()
        )
        if meta and not force:
            payload_out = _serialize_metadata(meta, include_raw)
            cache.set(_cache_key(image_uuid, resolved_variant, include_raw), payload_out, timeout=_METADATA_CACHE_TTL_SECONDS)
            return jsonify({"success": True, "data": payload_out, "cached": False, "updated": False})

        try:
            meta_result = extract_image_metadata(image_path=Path(image_path))
            meta = upsert_image_metadata(
                db,
                image_uuid=image_uuid,
                image_variant=resolved_variant,
                encounter_file_id=encounter_id,
                direct_image_upload_id=direct_id,
                metadata=meta_result,
            )
        except Exception as exc:
            _LOGGER.warning(
                "Metadata extraction failed for %s: %s",
                sanitize_log_value(image_uuid),
                sanitize_log_value(exc),
            )
            return jsonify({"success": False, "error": "Metadata extraction failed"}), 500

        payload_out = _serialize_metadata(meta, include_raw)

    cache.set(_cache_key(image_uuid, resolved_variant, include_raw), payload_out, timeout=_METADATA_CACHE_TTL_SECONDS)
    return jsonify({"success": True, "data": payload_out, "cached": False, "updated": True})
