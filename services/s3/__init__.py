"""Shared S3 service APIs."""

from .storage import (
    S3UploadMetadata,
    generate_hmac_media_url,
    get_storage_backend_info_for_hospital,
    upload_local_path_to_hospital_s3,
    upload_thumbnail_to_hospital_s3,
)

__all__ = [
    "S3UploadMetadata",
    "generate_hmac_media_url",
    "get_storage_backend_info_for_hospital",
    "upload_local_path_to_hospital_s3",
    "upload_thumbnail_to_hospital_s3",
]
