"""
Image processing utilities for thumbnail generation and image optimization.

This module provides functions for generating thumbnails, optimizing images,
and handling various image formats used in the Fundus Image Manager.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Tuple, Union
from PIL import Image, ImageOps
from io import BytesIO
from utils.log_sanitize import sanitize_log_value

# Configure logger
logger = logging.getLogger(__name__)

# Thumbnail configuration
THUMBNAIL_SIZE = (180, 180)  # 180px × 180px
THUMBNAIL_QUALITY = 85  # JPEG quality (85% as specified)
THUMBNAIL_PREFIX = "thm_"

# Supported image formats for thumbnail generation
SUPPORTED_FORMATS = {
    'JPEG', 'JPG', 'PNG', 'WEBP', 'BMP', 'GIF'
}

# Maximum image size for processing (to prevent memory issues)
MAX_IMAGE_SIZE = (50 * 1024 * 1024)  # 50MB


def generate_thumbnail(
    source_path: Union[str, Path],
    output_path: Union[str, Path],
    size: Tuple[int, int] = THUMBNAIL_SIZE,
    quality: int = THUMBNAIL_QUALITY,
    format_override: Optional[str] = None
) -> bool:
    """
    Generate a thumbnail from a source image.

    Args:
        source_path: Path to the source image file
        output_path: Path where the thumbnail will be saved
        size: Thumbnail size as (width, height) tuple
        quality: JPEG quality (1-100)
        format_override: Force output format (auto-detected if None)

    Returns:
        True if thumbnail was generated successfully, False otherwise

    Raises:
        FileNotFoundError: If source image doesn't exist
        ValueError: If image format is not supported
        OSError: If there are file system errors
    """
    source_path = Path(source_path)
    output_path = Path(output_path)

    try:
        # Validate source file
        if not source_path.exists():
            logger.error(
                "Source image not found: %s",
                sanitize_log_value(source_path),
            )
            raise FileNotFoundError(f"Source image not found: {source_path}")

        # Check file size
        file_size = source_path.stat().st_size
        if file_size > MAX_IMAGE_SIZE:
            logger.error(
                "Image too large for processing: %s bytes",
                sanitize_log_value(file_size),
            )
            raise ValueError(f"Image too large for processing: {file_size} bytes")

        # Open and process image
        with Image.open(source_path) as img:
            # Verify image format is supported
            if img.format and img.format.upper() not in SUPPORTED_FORMATS:
                logger.error(
                    "Unsupported image format: %s",
                    sanitize_log_value(img.format),
                )
                raise ValueError(f"Unsupported image format: {img.format}")

            # Convert palette / alpha modes to RGB (JPEG output cannot encode
            # mode P, and transparency is composited on black).
            if img.mode == 'P':
                img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')
            if img.mode in ('RGBA', 'LA'):
                # Create black background for transparent images
                background = Image.new('RGB', img.size, (0, 0, 0))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background

            # Generate thumbnail while preserving original aspect ratio.
            # The larger dimension is constrained to the requested size.
            img.thumbnail(size, Image.Resampling.LANCZOS)

            # Determine output format
            if format_override:
                output_format = format_override.upper()
            else:
                # Default to JPEG for better compression
                output_format = 'JPEG'

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save thumbnail
            save_kwargs = {}
            if output_format in ['JPEG', 'JPG']:
                save_kwargs = {
                    'format': 'JPEG',
                    'quality': quality,
                    'optimize': True,
                    'progressive': True
                }
            elif output_format == 'PNG':
                save_kwargs = {
                    'format': 'PNG',
                    'optimize': True
                }
            elif output_format == 'WEBP':
                save_kwargs = {
                    'format': 'WEBP',
                    'quality': quality,
                    'optimize': True
                }
            else:
                save_kwargs = {'format': output_format}

            img.save(output_path, **save_kwargs)

            # Verify thumbnail was created
            if not output_path.exists():
                logger.error(
                    "Thumbnail not created: %s",
                    sanitize_log_value(output_path),
                )
                return False

            thumbnail_size = output_path.stat().st_size
            logger.info(
                "Thumbnail generated successfully: %s (%s bytes, %s)",
                sanitize_log_value(output_path),
                sanitize_log_value(thumbnail_size),
                sanitize_log_value(output_format),
            )

            return True

    except Exception as e:
        logger.error(
            "Failed to generate thumbnail from %s: %s",
            sanitize_log_value(source_path),
            sanitize_log_value(e),
        )
        # Clean up partial thumbnail if it exists
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass
        return False


def generate_thumbnail_from_bytes(
    image_data: bytes,
    output_path: Union[str, Path],
    size: Tuple[int, int] = THUMBNAIL_SIZE,
    quality: int = THUMBNAIL_QUALITY,
    format_override: Optional[str] = None
) -> tuple[bool, str]:
    """
    Generate a thumbnail from image data (bytes).

    This is useful when you have image data in memory rather than a file.

    Args:
        image_data: Raw image data as bytes
        output_path: Path where the thumbnail will be saved
        size: Thumbnail size as (width, height) tuple
        quality: JPEG quality (1-100)
        format_override: Force output format (auto-detected if None)

    Returns:
        (success, message) with a human-readable reason.
    """
    try:
        # Check data size
        if len(image_data) > MAX_IMAGE_SIZE:
            message = f"Image data too large: {len(image_data)} bytes"
            logger.error(message)
            return False, message

        # Create BytesIO object from image data
        with BytesIO(image_data) as img_stream:
            # Open and process image
            with Image.open(img_stream) as img:
                # Use existing generate_thumbnail function with a temporary file
                import tempfile
                temp_path = None
                with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
                    temp_file.write(image_data)
                    temp_path = temp_file.name

                try:
                    success = generate_thumbnail(
                        temp_path, output_path, size, quality, format_override
                    )
                    return success, "Thumbnail generated successfully" if success else "Thumbnail generation failed"
                finally:
                    # Clean up temporary file
                    if temp_path:
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            pass

    except (OSError, ValueError) as e:
        message = f"Failed to generate thumbnail from bytes: {str(e)}"
        logger.error(message)
        return False, message


def get_thumbnail_filename(original_filename: str) -> str:
    """
    Generate thumbnail filename using the thm_uuid.filetype convention.

    Args:
        original_filename: Original image filename (should be UUID-based)

    Returns:
        Thumbnail filename (e.g., "thm_abc123.jpg")

    Examples:
        >>> get_thumbnail_filename("abc123.jpg")
        'thm_abc123.jpg'
        >>> get_thumbnail_filename("abc123.png")
        'thm_abc123.png'
    """
    # Handle both UUID filenames and regular filenames
    name_part = Path(original_filename).stem
    extension = Path(original_filename).suffix.lower()

    # For JPEG, use .jpg extension consistently
    if extension in ['.jpeg', '.jpg']:
        extension = '.jpg'

    return f"{THUMBNAIL_PREFIX}{name_part}{extension}"


def is_supported_image_format(file_path: Union[str, Path]) -> bool:
    """
    Check if a file is a supported image format for thumbnail generation.

    Args:
        file_path: Path to the image file

    Returns:
        True if format is supported, False otherwise
    """
    try:
        with Image.open(file_path) as img:
            return img.format and img.format.upper() in SUPPORTED_FORMATS
    except Exception:
        return False


def get_image_info(file_path: Union[str, Path]) -> dict:
    """
    Get basic information about an image file.

    Args:
        file_path: Path to the image file

    Returns:
        Dictionary with image information (format, size, mode, etc.)
        Returns empty dict if file cannot be processed
    """
    try:
        with Image.open(file_path) as img:
            file_stat = Path(file_path).stat()

            return {
                'format': img.format,
                'mode': img.mode,
                'size': img.size,
                'file_size': file_stat.st_size,
                'has_transparency': (
                    img.mode in ('RGBA', 'LA') or
                    (img.mode == 'P' and 'transparency' in img.info)
                )
            }
    except Exception as e:
        logger.error(
            "Failed to get image info for %s: %s",
            sanitize_log_value(file_path),
            sanitize_log_value(e),
        )
        return {}


def optimize_image(
    source_path: Union[str, Path],
    output_path: Union[str, Path],
    quality: int = 85,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None
) -> bool:
    """
    Optimize an image for web use by resizing and compressing.

    Args:
        source_path: Path to the source image file
        output_path: Path where optimized image will be saved
        quality: Output quality (1-100)
        max_width: Maximum width (None if no resize)
        max_height: Maximum height (None if no resize)

    Returns:
        True if optimization was successful, False otherwise
    """
    try:
        with Image.open(source_path) as img:
            # Resize if necessary
            if max_width or max_height:
                img.thumbnail(
                    (max_width or img.size[0], max_height or img.size[1]),
                    Image.Resampling.LANCZOS
                )

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save optimized image
            if img.format and img.format.upper() in ['JPEG', 'JPG']:
                img.save(output_path, 'JPEG', quality=quality, optimize=True, progressive=True)
            elif img.format and img.format.upper() == 'PNG':
                img.save(output_path, 'PNG', optimize=True)
            else:
                # Default to JPEG for unknown formats
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                img.save(output_path, 'JPEG', quality=quality, optimize=True, progressive=True)

            return True

    except Exception as e:
        logger.error(
            "Failed to optimize image %s: %s",
            sanitize_log_value(source_path),
            sanitize_log_value(e),
        )
        return False


# Convenience functions for common operations
def create_thumbnail_for_image(
    image_path: Union[str, Path],
    thumbnail_dir: Optional[Union[str, Path]] = None
) -> Optional[Path]:
    """
    Create a thumbnail for an image in the same directory or specified directory.

    Args:
        image_path: Path to the source image
        thumbnail_dir: Directory for thumbnail (same as image if None)

    Returns:
        Path to the generated thumbnail, or None if failed
    """
    image_path = Path(image_path)

    if thumbnail_dir:
        thumbnail_dir = Path(thumbnail_dir)
    else:
        thumbnail_dir = image_path.parent

    thumbnail_filename = get_thumbnail_filename(image_path.name)
    thumbnail_path = thumbnail_dir / thumbnail_filename

    if generate_thumbnail(image_path, thumbnail_path):
        return thumbnail_path
    return None


# JPEG segments that carry no pixel data and may carry identifiers: APP1 (Exif/XMP), APP3-APP13
# (IPTC, Photoshop, ...), APP15 and comments. APP0 JFIF, APP2 ICC colour profile and APP14 Adobe
# (colour transform) change how pixels are interpreted, so they are kept.
_JPEG_STANDALONE = frozenset({0x01, *range(0xD0, 0xD9)})


def _strip_jpeg_metadata(data: bytes) -> bytes | None:
    """Drop metadata segments from a JPEG without touching the compressed image data.

    Returns None when ``data`` is not a JPEG this parser understands, so the caller can fall back.
    """
    if data[:2] != b"\xff\xd8":
        return None
    out = bytearray(b"\xff\xd8")
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker in _JPEG_STANDALONE:
            out += data[pos:pos + 2]
            pos += 2
            continue
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        if length < 2 or pos + 2 + length > len(data):
            return None
        segment = data[pos:pos + 2 + length]
        payload = segment[4:]
        if marker == 0xDA:  # start of scan: the rest is entropy-coded data up to EOI
            out += segment
            rest = data[pos + 2 + length:]
            end = rest.find(b"\xff\xd9")
            out += rest if end < 0 else rest[:end + 2]  # anything appended after EOI is dropped
            return bytes(out)
        keep = not (
            marker == 0xFE
            or marker == 0xE1
            or 0xE3 <= marker <= 0xED
            or marker == 0xEF
            or (marker == 0xE0 and not payload.startswith(b"JFIF\x00"))
            or (marker == 0xE2 and not payload.startswith(b"ICC_PROFILE\x00"))
            or (marker == 0xEE and not payload.startswith(b"Adobe"))
        )
        if keep:
            out += segment
        pos += 2 + length
    return None


def strip_exif_data(image_data: bytes) -> bytes:
    """
    Strip EXIF and other metadata from an image byte stream without changing the pixels.

    JPEGs are rewritten segment by segment, so the compressed image data is byte-identical
    (no re-encoding, no quality loss, no resizing). Other formats are rebuilt from their pixels
    in a lossless way; a JPEG this parser cannot read is re-encoded at maximum quality.

    Args:
        image_data: Raw image data as bytes

    Returns:
        Cleaned image data as bytes. Returns original data if processing fails.
    """
    try:
        if not image_data:
            return image_data

        stripped = _strip_jpeg_metadata(image_data)
        if stripped is not None:
            return stripped

        with BytesIO(image_data) as in_stream:
            with Image.open(in_stream) as img:
                clean_img = Image.new(img.mode, img.size)
                clean_img.putdata(list(img.getdata()))
                fmt = img.format or 'JPEG'
                save_kwargs = {"quality": 100, "subsampling": 0} if fmt == "JPEG" else {}
                with BytesIO() as out_stream:
                    clean_img.save(out_stream, format=fmt, **save_kwargs)
                    return out_stream.getvalue()

    except Exception as e:
        logger.error(
            "Failed to strip EXIF data: %s",
            sanitize_log_value(e)
        )
        return image_data
