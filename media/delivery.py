"""Deliver one already-authorized media object from S3 or local storage.

Callers resolve and authorize the :class:`AuthorizedMediaSource` first (signed
URL, session policy, or a project sync grant); this module only chooses the
storage backend and variant.
"""

from __future__ import annotations

import logging

from flask import abort, redirect

from media.authorization import AuthorizedMediaSource, MediaSourceType
from models import DirectImageUpload, EncounterFile, EncounterFilePDF, EncounterSetImage, S3Config
from utils.log_sanitize import sanitize_log_value
from utils.utilsImgServe import (
    directImgEdByUUID,
    directImgFinalThumbnailByUUID,
    directImgOrigByUUID,
    encounterImageByUUID,
    encounterImageThumbnailByUUID,
    encounterPDFByUUID,
    encounterSetImageByUUID,
    encounterSetImageEditedByUUID,
    encounterSetImageOriginalByUUID,
    encounterSetImageThumbnailByUUID,
)

logger = logging.getLogger(__name__)

_MODEL_BY_SOURCE = {
    MediaSourceType.DIRECT_IMAGE_UPLOAD: DirectImageUpload,
    MediaSourceType.ENCOUNTER_FILE: EncounterFile,
    MediaSourceType.ENCOUNTER_FILE_PDF: EncounterFilePDF,
    MediaSourceType.ENCOUNTER_SET_IMAGE: EncounterSetImage,
}


def deliver_media(db, resource: AuthorizedMediaSource, *, variant: str, exact_original: bool = False):
    """Return a Flask response for ``variant`` ("original", "edited", "thumbnail").

    ``exact_original`` serves the unedited EncounterSet capture for
    ``original``; the viewer default instead prefers the edited file.
    """
    model = _MODEL_BY_SOURCE.get(resource.source_type)
    row = db.get(model, resource.source_id) if model is not None else None
    if row is None:
        abort(404)
    if variant == "edited":
        object_key = getattr(row, "s3_object_key_edited", None)
    elif variant == "thumbnail":
        object_key = (
            getattr(row, "s3_object_key_edited_thumbnail", None)
            or getattr(row, "s3_object_key_thumbnail", None)
        )
    else:
        object_key = getattr(row, "s3_object_key", None)
    s3_config_id = getattr(row, "s3_config_id", None)
    if s3_config_id and object_key:
        from utils.s3_storage_backends import generate_presigned_url, get_s3_client

        s3_config = db.get(S3Config, s3_config_id)
        if s3_config and s3_config.is_active:
            try:
                kwargs = {"expires_in": 120} if variant == "thumbnail" else {}
                url = generate_presigned_url(get_s3_client(s3_config), s3_config, object_key, **kwargs)
                return redirect(url, code=307)
            except Exception as exc:  # noqa: BLE001 - storage fallback is intentional
                logger.warning(
                    "S3 media redirect failed uuid=%s error=%s",
                    sanitize_log_value(resource.uuid),
                    sanitize_log_value(exc),
                )

    uuid_str = resource.uuid
    if resource.source_type == MediaSourceType.DIRECT_IMAGE_UPLOAD:
        if variant == "edited":
            return directImgEdByUUID(uuid_str, preauthorized=resource)
        if variant == "thumbnail":
            return directImgFinalThumbnailByUUID(uuid_str, preauthorized=resource)
        return directImgOrigByUUID(uuid_str, preauthorized=resource)
    if resource.source_type == MediaSourceType.ENCOUNTER_FILE:
        if variant == "thumbnail":
            return encounterImageThumbnailByUUID(uuid_str, preauthorized=resource)
        return encounterImageByUUID(uuid_str, preauthorized=resource)
    if resource.source_type == MediaSourceType.ENCOUNTER_SET_IMAGE:
        if variant == "edited":
            return encounterSetImageEditedByUUID(uuid_str, preauthorized=resource)
        if variant == "thumbnail":
            return encounterSetImageThumbnailByUUID(uuid_str, preauthorized=resource)
        if exact_original:
            return encounterSetImageOriginalByUUID(uuid_str, preauthorized=resource)
        return encounterSetImageByUUID(uuid_str, preauthorized=resource)
    return encounterPDFByUUID(uuid_str, preauthorized=resource)
