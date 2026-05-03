"""Shared S3 helpers for upload, media, sync, and inference services."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.log_sanitize import sanitize_log_value
from utils.s3_paths import s3_key_from_local_path
from utils.s3_upload_handler import get_active_s3_config, get_storage_backend_info, upload_file_to_s3
from utils.s3_url_signing import generate_media_url


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3UploadMetadata:
    s3_config_id: int
    s3_object_key: str
    backend: str
    provider: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "s3_config_id": self.s3_config_id,
            "s3_object_key": self.s3_object_key,
            "backend": self.backend,
            "provider": self.provider,
        }


def upload_local_path_to_hospital_s3(
    *,
    hospital_id: int,
    file_content: bytes,
    local_path,
    file_type: str = "original",
) -> S3UploadMetadata | None:
    """Upload a locally mirrored file to the hospital S3 backend, falling back to local on failure."""
    try:
        s3_config = get_active_s3_config(hospital_id)
        if not s3_config:
            return None

        object_key = s3_key_from_local_path(local_path)
        upload_file_to_s3(s3_config, file_content, object_key)
        logger.info(
            "S3 upload successful for hospital_id=%s, file_type=%s, filename=%s, object_key=%s",
            sanitize_log_value(hospital_id),
            sanitize_log_value(file_type),
            sanitize_log_value(Path(local_path).name),
            sanitize_log_value(object_key),
        )
        return S3UploadMetadata(
            s3_config_id=s3_config.id,
            s3_object_key=object_key,
            backend="s3",
            provider=s3_config.provider,
        )
    except Exception as exc:
        logger.error(
            "S3 upload failed for hospital_id=%s, filename=%s: %s",
            sanitize_log_value(hospital_id),
            sanitize_log_value(Path(local_path).name if local_path else ""),
            sanitize_log_value(exc),
        )
        logger.info("S3 upload failed, local fallback available.")
        return None


def upload_thumbnail_to_hospital_s3(*, hospital_id: int, thumbnail_content: bytes, thumbnail_path) -> S3UploadMetadata | None:
    return upload_local_path_to_hospital_s3(
        hospital_id=hospital_id,
        file_content=thumbnail_content,
        local_path=thumbnail_path,
        file_type="thumbnail",
    )


def generate_hmac_media_url(*, file_uuid: str, hospital_id: int, variant: str = "orig") -> str | None:
    try:
        return generate_media_url(file_uuid, hospital_id, variant=variant)
    except Exception as exc:
        logger.warning(
            "Failed to generate HMAC URL for uuid=%s, hospital_id=%s: %s",
            sanitize_log_value(file_uuid),
            sanitize_log_value(hospital_id),
            sanitize_log_value(exc),
        )
        return None


def get_storage_backend_info_for_hospital(hospital_id: int) -> dict:
    return get_storage_backend_info(hospital_id)
