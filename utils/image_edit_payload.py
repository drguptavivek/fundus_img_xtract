from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError


_EXTENSION_BY_FORMAT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


class InvalidImageEditPayload(ValueError):
    """Raised when an editor payload is not a supported encoded image."""


@dataclass(frozen=True)
class DecodedImageEdit:
    content: bytes
    extension: str


def decode_image_edit_payload(value: str) -> DecodedImageEdit:
    """Decode and verify a canvas image payload, deriving extension from bytes."""
    if not isinstance(value, str) or not value:
        raise InvalidImageEditPayload("Image data is required.")
    encoded = value.split(",", 1)[1] if value.startswith("data:image") and "," in value else value
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageEditPayload("Invalid base64 image data.") from exc
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = str(image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageEditPayload("Decoded payload is not a valid image.") from exc
    extension = _EXTENSION_BY_FORMAT.get(image_format)
    if extension is None:
        raise InvalidImageEditPayload("Edited images must be JPEG, PNG, or WebP.")
    return DecodedImageEdit(content=content, extension=extension)
