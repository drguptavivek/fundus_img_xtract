from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import ExifTags, Image
from PIL import IptcImagePlugin

from auth.utils import utcnow
from models import ImageMetadata
from utils.log_sanitize import sanitize_log_value

_LOGGER = logging.getLogger("image_metadata")


@dataclass(frozen=True)
class ImageMetaResult:
    width: Optional[int]
    height: Optional[int]
    format: Optional[str]
    mode: Optional[str]
    bit_depth: Optional[int]
    is_grayscale: Optional[bool]
    has_alpha: Optional[bool]
    file_size_bytes: Optional[int]
    dpi_x: Optional[float]
    dpi_y: Optional[float]
    avg_luminance: Optional[float]
    max_luminance: Optional[float]
    luminance_std: Optional[float]
    mean_r: Optional[float]
    mean_g: Optional[float]
    mean_b: Optional[float]
    median_r: Optional[float]
    median_g: Optional[float]
    median_b: Optional[float]
    histogram_json: Optional[str]
    exif_json: Optional[str]
    iptc_json: Optional[str]


def _bit_depth_from_mode(mode: str | None) -> Optional[int]:
    if not mode:
        return None
    mapping = {
        "1": 1,
        "L": 8,
        "P": 8,
        "RGB": 8,
        "RGBA": 8,
        "CMYK": 8,
        "YCbCr": 8,
        "I;16": 16,
        "I;16B": 16,
        "I;16L": 16,
        "I": 32,
        "F": 32,
        "LA": 8,
    }
    return mapping.get(mode)


def _encode_raw_bytes(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return None


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _extract_exif_json(img: Image.Image) -> Optional[str]:
    exif_raw = img.info.get("exif")
    exif_dict: Dict[str, Any] = {}
    try:
        exif = img.getexif()
        for tag_id, value in exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            exif_dict[tag_name] = _safe_json_value(value)
    except Exception:
        exif_dict = {}

    if not exif_raw and not exif_dict:
        return None
    payload = {
        "raw_base64": _encode_raw_bytes(exif_raw),
        "tags": exif_dict,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _extract_iptc_json(img: Image.Image) -> Optional[str]:
    iptc_raw = img.info.get("iptc")
    iptc_dict: Dict[str, Any] = {}
    try:
        iptc_info = IptcImagePlugin.getiptcinfo(img)
        if iptc_info:
            for key, value in iptc_info.items():
                if isinstance(key, tuple):
                    key_str = f"{key[0]}:{key[1]}"
                else:
                    key_str = str(key)
                iptc_dict[key_str] = _safe_json_value(value)
    except Exception:
        iptc_dict = {}

    if not iptc_raw and not iptc_dict:
        return None
    payload = {
        "raw_base64": _encode_raw_bytes(iptc_raw),
        "tags": iptc_dict,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _compute_stats(img: Image.Image) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], list[int]]:
    rgb_img = img.convert("RGB")
    arr = np.asarray(rgb_img)
    if arr.size == 0:
        return {}, {}, {}, []

    mean = {
        "r": float(arr[..., 0].mean()),
        "g": float(arr[..., 1].mean()),
        "b": float(arr[..., 2].mean()),
    }
    median = {
        "r": float(np.median(arr[..., 0])),
        "g": float(np.median(arr[..., 1])),
        "b": float(np.median(arr[..., 2])),
    }

    luminance = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    lum_stats = {
        "avg": float(luminance.mean()),
        "max": float(luminance.max()),
        "std": float(luminance.std()),
    }
    hist, _ = np.histogram(luminance, bins=16, range=(0, 255))
    return mean, median, lum_stats, hist.astype(int).tolist()


def _detect_grayscale(img: Image.Image, rgb_img: Image.Image) -> Optional[bool]:
    if img.mode in ("L", "1", "LA"):
        return True
    if rgb_img.mode != "RGB":
        return None
    arr = np.asarray(rgb_img)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    h, w, _ = arr.shape
    step_y = max(1, h // 100)
    step_x = max(1, w // 100)
    sample = arr[::step_y, ::step_x, :3]
    return bool(np.all(sample[..., 0] == sample[..., 1]) and np.all(sample[..., 1] == sample[..., 2]))


def extract_image_metadata(
    image_path: Optional[Path] = None,
    image_bytes: Optional[bytes] = None,
    file_size_bytes: Optional[int] = None,
) -> ImageMetaResult:
    try:
        if image_bytes is not None:
            stream = BytesIO(image_bytes)
            img = Image.open(stream)
        elif image_path is not None:
            img = Image.open(str(image_path))
        else:
            raise ValueError("image_path or image_bytes required")

        img.load()
        width, height = img.size
        fmt = img.format
        mode = img.mode
        bit_depth = _bit_depth_from_mode(mode)
        has_alpha = "A" in img.getbands()

        dpi_x = None
        dpi_y = None
        dpi = img.info.get("dpi")
        if isinstance(dpi, tuple) and len(dpi) >= 2:
            dpi_x = float(dpi[0]) if dpi[0] else None
            dpi_y = float(dpi[1]) if dpi[1] else None

        exif_json = _extract_exif_json(img)
        iptc_json = _extract_iptc_json(img)

        mean, median, lum_stats, hist = _compute_stats(img)
        rgb_img = img.convert("RGB")
        is_grayscale = _detect_grayscale(img, rgb_img)

        if file_size_bytes is None:
            if image_bytes is not None:
                file_size_bytes = len(image_bytes)
            elif image_path is not None:
                file_size_bytes = image_path.stat().st_size

        histogram_json = json.dumps(hist, ensure_ascii=True, separators=(",", ":")) if hist else None

        return ImageMetaResult(
            width=width,
            height=height,
            format=fmt,
            mode=mode,
            bit_depth=bit_depth,
            is_grayscale=is_grayscale,
            has_alpha=has_alpha,
            file_size_bytes=file_size_bytes,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
            avg_luminance=lum_stats.get("avg"),
            max_luminance=lum_stats.get("max"),
            luminance_std=lum_stats.get("std"),
            mean_r=mean.get("r"),
            mean_g=mean.get("g"),
            mean_b=mean.get("b"),
            median_r=median.get("r"),
            median_g=median.get("g"),
            median_b=median.get("b"),
            histogram_json=histogram_json,
            exif_json=exif_json,
            iptc_json=iptc_json,
        )
    except Exception as exc:
        _LOGGER.warning("Failed to extract image metadata: %s", sanitize_log_value(exc))
        return ImageMetaResult(
            width=None,
            height=None,
            format=None,
            mode=None,
            bit_depth=None,
            is_grayscale=None,
            has_alpha=None,
            file_size_bytes=file_size_bytes,
            dpi_x=None,
            dpi_y=None,
            avg_luminance=None,
            max_luminance=None,
            luminance_std=None,
            mean_r=None,
            mean_g=None,
            mean_b=None,
            median_r=None,
            median_g=None,
            median_b=None,
            histogram_json=None,
            exif_json=None,
            iptc_json=None,
        )


def upsert_image_metadata(
    db,
    *,
    image_uuid: str,
    image_variant: str,
    encounter_file_id: Optional[int] = None,
    direct_image_upload_id: Optional[int] = None,
    metadata: ImageMetaResult,
) -> ImageMetadata:
    existing = (
        db.query(ImageMetadata)
        .filter(
            ImageMetadata.image_uuid == image_uuid,
            ImageMetadata.image_variant == image_variant,
        )
        .first()
    )
    values = dict(
        encounter_file_id=encounter_file_id,
        direct_image_upload_id=direct_image_upload_id,
        width=metadata.width,
        height=metadata.height,
        format=metadata.format,
        mode=metadata.mode,
        bit_depth=metadata.bit_depth,
        is_grayscale=metadata.is_grayscale,
        has_alpha=metadata.has_alpha,
        file_size_bytes=metadata.file_size_bytes,
        dpi_x=metadata.dpi_x,
        dpi_y=metadata.dpi_y,
        avg_luminance=metadata.avg_luminance,
        max_luminance=metadata.max_luminance,
        luminance_std=metadata.luminance_std,
        mean_r=metadata.mean_r,
        mean_g=metadata.mean_g,
        mean_b=metadata.mean_b,
        median_r=metadata.median_r,
        median_g=metadata.median_g,
        median_b=metadata.median_b,
        histogram_json=metadata.histogram_json,
        exif_json=metadata.exif_json,
        iptc_json=metadata.iptc_json,
        updated_at=utcnow(),
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        db.add(existing)
        return existing

    record = ImageMetadata(
        image_uuid=image_uuid,
        image_variant=image_variant,
        created_at=utcnow(),
        **values,
    )
    db.add(record)
    return record
