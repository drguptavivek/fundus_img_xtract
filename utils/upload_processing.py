import logging
import os
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from models import (
    Session,
    EncounterFile,
    EncounterFilePDF,
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
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)

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

    # Determine Model based on type
    if file_type == 'encounter_file':
        model_cls = EncounterFile
    elif file_type == 'direct_upload':
        model_cls = DirectImageUpload
    else:
        raise ValueError(f"Unknown file_type: {file_type}")

    record = db_session.query(model_cls).get(file_id)
    if not record:
        raise ValueError(f"{file_type} with ID {file_id} not found")

    # Image Processing
    if path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}:
        thumb_filename = get_thumbnail_filename(path.name)
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

def process_file_metadata_strip(
    file_id: int,
    file_type: str,
    file_path: str,
    db_session: Session
) -> dict:
    """
    Phase 2: Data Processing (Metadata + Strip).
    - Extract Metadata to DB.
    - Strip EXIF/IPTC from file on disk.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if file_type == 'encounter_file':
        model_cls = EncounterFile
        # EncounterFiles have a UUID field
        record = db_session.query(model_cls).get(file_id)
        if not record:
             raise ValueError(f"{file_type} with ID {file_id} not found")
        image_uuid = str(record.uuid)
        encounter_file_id = record.id
        direct_upload_id = None
    elif file_type == 'direct_upload':
        model_cls = DirectImageUpload
        record = db_session.query(model_cls).get(file_id)
        if not record:
             raise ValueError(f"{file_type} with ID {file_id} not found")
        image_uuid = str(record.uuid)
        encounter_file_id = None
        direct_upload_id = record.id
    else:
        raise ValueError(f"Unknown file_type: {file_type}")

    # 1. Extract Metadata
    try:
        # We read the file to extract metadata
        metadata_result = extract_image_metadata(image_path=path)
        
        # Save to DB
        upsert_image_metadata(
            db_session,
            image_uuid=image_uuid,
            image_variant="orig",
            encounter_file_id=encounter_file_id,
            direct_image_upload_id=direct_upload_id,
            metadata=metadata_result
        )
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        logger.error(f"Metadata extraction failed for {path}: {sanitize_log_value(e)}")
        # We continue to stripping even if metadata fails, or should we abort?
        # Usually better to ensure privacy (strip) even if extraction fails.
    
    # 2. Strip EXIF/IPTC
    try:
        with open(path, "rb") as f:
            content = f.read()
        
        clean_content = strip_exif_data(content)
        
        if len(clean_content) != len(content):
            with open(path, "wb") as f:
                f.write(clean_content)
            logger.info(f"Stripped EXIF from {path} ({len(content)} -> {len(clean_content)} bytes)")
    except Exception as e:
        logger.error(f"Failed to strip EXIF from {path}: {sanitize_log_value(e)}")
        return {"status": "error", "message": str(e)}

    return {"status": "ok"}
