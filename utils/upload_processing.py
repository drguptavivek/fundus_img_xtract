import logging
import os
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from models import (
    Session,
    EncounterFile,
    EncounterFilePDF,
    EncounterSetImage,
    ImageMetadata,
    DirectImageUpload
)
from utils.image_processing import (
    generate_thumbnail, 
    get_thumbnail_filename, 
    strip_exif_data
)
from utils.image_metadata import (
    extract_image_metadata, 
    upsert_image_metadata
)
from utils.pii_verification import upsert_pii_verification
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)
metadata_logger = logging.getLogger("image_metadata")
pii_logger = logging.getLogger("pii_detection")

def process_file_visual(
    file_id: int, 
    file_type: str,  # 'encounter_file' or 'direct_upload'
    file_path: str,
    db_session: Session
) -> dict:
    """
    Phase 1: Visual Processing (Thumbnail / OCR placeholder).
    - Generates thumbnail for images.
    - (Future) Trigger OCR for PDFs.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    result = {"status": "ok", "thumbnail": None}

    if file_type == 'encounter_file':
        model_cls = EncounterFile
    elif file_type == 'direct_upload':
        model_cls = DirectImageUpload
    elif file_type == 'encounter_set_image':
        model_cls = EncounterSetImage
    else:
        raise ValueError(f"Unknown file_type: {file_type}")

    record = db_session.query(model_cls).get(file_id)
    if not record:
        raise ValueError(f"{file_type} with ID {file_id} not found")

    # Image Processing
    if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
        thumb_filename = get_thumbnail_filename(path.name)
        if file_type == 'encounter_set_image':
            thumb_dir = path.parent / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumb_dir / thumb_filename
        else:
            thumb_path = path.parent / thumb_filename
        
        success = generate_thumbnail(path, thumb_path)
        if success:
            record.thumbnail_filename = thumb_filename
            result["thumbnail"] = thumb_filename
            # Commit the thumbnail update immediately so UI sees it
            db_session.commit() 
        else:
            logger.error(f"Failed to generate thumbnail for {path}")
            result["status"] = "warning"
            result["error"] = "Thumbnail generation failed"

    # PDF Processing (Placeholder for now, OCR logic is separate)
    elif path.suffix.lower() == '.pdf':
        pass

    return result

def process_file_data_pipeline(
    file_id: int,
    file_type: str,
    file_path: str,
    db_session: Session,
    run_metadata: bool = True,
    run_pii: bool = True,
    run_strip: bool = True,
    *,
    image_variant: str = "orig",
    commit: bool = True,
) -> dict:
    """
    Flexible Data Pipeline:
    - Metadata Extraction (Technical + EXIF/IPTC)
    - PII Detection (OCR on pixels)
    - Privacy Stripping (EXIF/IPTC removal)
    
    Optimized to load file bytes once if multiple stages are requested.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Resolve UUID and IDs
    if file_type == 'encounter_file':
        record = db_session.query(EncounterFile).get(file_id)
        if not record: raise ValueError(f"EncounterFile {file_id} not found")
        image_uuid, encounter_file_id, direct_upload_id = str(record.uuid), record.id, None
    elif file_type == 'direct_upload':
        record = db_session.query(DirectImageUpload).get(file_id)
        if not record: raise ValueError(f"DirectImageUpload {file_id} not found")
        image_uuid, encounter_file_id, direct_upload_id = str(record.uuid), None, record.id
    elif file_type == 'encounter_set_image':
        record = db_session.query(EncounterSetImage).get(file_id)
        if not record: raise ValueError(f"EncounterSetImage {file_id} not found")
        image_uuid, encounter_file_id, direct_upload_id = str(record.uuid), None, None
    else:
        raise ValueError(f"Unknown file_type: {file_type}")

    # Load bytes once
    content = None
    if run_metadata or run_pii or run_strip:
        with open(path, "rb") as f:
            content = f.read()

    result = {"status": "ok", "metadata_ok": False, "pii_ok": False, "strip_ok": False}

    # 1. Metadata Stage
    if run_metadata and content:
        try:
            metadata_result = extract_image_metadata(image_bytes=content)
            upsert_image_metadata(
                db_session,
                image_uuid=image_uuid,
                image_variant=image_variant,
                encounter_file_id=encounter_file_id,
                direct_image_upload_id=direct_upload_id,
                metadata=metadata_result
            )
            metadata_logger.info(f"Metadata extracted and saved for {path}")
            result["metadata_ok"] = True
        except Exception as e:
            metadata_logger.error(f"Metadata extraction failed for {path}: {sanitize_log_value(e)}")

    # 2. PII Stage
    if run_pii and content:
        try:
            import cv2
            import numpy as np
            from utils.ocr_pii import detect_pii_details_for_image

            nparr = np.frombuffer(content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                ocr_result = detect_pii_details_for_image(img)
                upsert_pii_verification(
                    db_session,
                    image_uuid=image_uuid,
                    image_variant=image_variant,
                    ocr_result=ocr_result
                )
                is_pii = ocr_result.get("is_pii", False)
                pii_logger.info(f"PII detection complete for {path}. Result: PII={is_pii}")
                result["pii_ok"] = True
            else:
                pii_logger.warning(f"Failed to decode image for PII: {path}")
        except Exception as e:
            pii_logger.error(f"PII detection failed for {path}: {sanitize_log_value(e)}")

    # 3. Strip Stage
    if run_strip and content:
        try:
            clean_content = strip_exif_data(content)
            if len(clean_content) != len(content):
                with open(path, "wb") as f:
                    f.write(clean_content)
                logger.info(f"Stripped EXIF from {path} ({len(content)} -> {len(clean_content)} bytes)")
            result["strip_ok"] = True
        except Exception as e:
            logger.error(f"Failed to strip EXIF from {path}: {sanitize_log_value(e)}")

    if commit:
        db_session.commit()
    return result
