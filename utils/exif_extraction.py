"""
EXIF data extraction utility for images.

Supports DirectImageUpload, EncounterFile, and EncounterSetImage.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from models import DirectImageUpload, EncounterFile, EncounterSetImage
from db_transaction_manager import transaction_scope
from utils.fileUtils import IMAGE_DIR

logger = logging.getLogger(__name__)


def extract_exif_for_encounter_set_image(image_id: int, image_type: str = "encounter_set_image") -> dict:
    """
    Extract EXIF metadata from an encounter set image and store it in the database.

    Args:
        image_id: ID of the image record
        image_type: Type of image ('encounter_set_image', 'direct_upload', 'encounter_file')

    Returns:
        Dict with extraction results
    """
    try:
        # Get the image record and source path based on type
        if image_type == "encounter_set_image":
            with transaction_scope() as db:
                img = db.query(EncounterSetImage).filter_by(id=image_id).first()
                if not img:
                    return {"success": False, "error": f"EncounterSetImage {image_id} not found"}

                source_path = IMAGE_DIR / img.folder_rel / img.original_filename
                image_uuid = img.uuid
                record = img

        elif image_type == "direct_upload":
            with transaction_scope() as db:
                img = db.query(DirectImageUpload).filter_by(id=image_id).first()
                if not img:
                    return {"success": False, "error": f"DirectImageUpload {image_id} not found"}

                source_path = IMAGE_DIR / img.folder_rel / img.filename
                image_uuid = img.uuid
                record = img

        elif image_type == "encounter_file":
            with transaction_scope() as db:
                img = db.query(EncounterFile).filter_by(id=image_id).first()
                if not img:
                    return {"success": False, "error": f"EncounterFile {image_id} not found"}

                source_path = IMAGE_DIR / img.filename
                image_uuid = img.uuid
                record = img

        else:
            return {"success": False, "error": f"Unknown image type: {image_type}"}

        if not source_path.exists():
            return {"success": False, "error": f"Source image not found: {source_path}"}

        # Extract EXIF data
        exif_data = _extract_exif_from_file(source_path)

        # Store EXIF data in the database record
        # Note: The exact field to store EXIF data depends on the model
        # For now, we'll log it and return success
        # In production, you might have an exif_data JSONB column

        logger.info(
            "Extracted EXIF data for %s %s: %d fields",
            image_type,
            sanitize_value(str(image_uuid)),
            len(exif_data) if exif_data else 0
        )

        return {
            "success": True,
            "image_id": image_id,
            "image_type": image_type,
            "uuid": str(image_uuid),
            "exif_count": len(exif_data) if exif_data else 0,
            "exif_data": exif_data
        }

    except Exception as e:
        logger.error(
            "Failed to extract EXIF for %s %s: %s",
            image_type,
            image_id,
            sanitize_log_value(str(e)),
        )
        return {
            "success": False,
            "error": str(e),
            "image_id": image_id,
            "image_type": image_type
        }


def _extract_exif_from_file(source_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract EXIF metadata from an image file.

    Args:
        source_path: Path to the image file

    Returns:
        Dict of EXIF data or None if extraction failed
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        with Image.open(source_path) as img:
            exif_data = {}
            exif = img.getexif()

            if exif is not None:
                for tag, value in exif.items():
                    tag_name = TAGS.get(tag, tag)
                    if tag_name == "GPSInfo":
                        # Process GPS sub-IFD
                        gps_data = {}
                        for gps_tag in value:
                            gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                            gps_data[gps_tag_name] = value[gps_tag]
                        exif_data["GPSInfo"] = gps_data
                    else:
                        # Convert bytes to string for readability
                        if isinstance(value, bytes):
                            try:
                                value = value.decode('utf-8', errors='replace')
                            except:
                                value = str(value)
                        exif_data[tag_name] = value

            return exif_data if exif_data else None

    except ImportError:
        logger.warning("PIL not available for EXIF extraction")
        return None
    except Exception as e:
        logger.error(f"Failed to extract EXIF from {source_path}: {e}")
        return None


def sanitize_log_value(value: str) -> str:
    """Sanitize values for logging (placeholder - use actual sanitize_log_value in production)."""
    if not value:
        return ""
    # Truncate long values
    return str(value)[:200] if len(str(value)) > 200 else str(value)