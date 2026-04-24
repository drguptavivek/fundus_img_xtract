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

            # Convert RGBA to RGB if necessary (for JPEG output)
            if img.mode in ('RGBA', 'LA', 'P'):
                if img.mode == 'P' and 'transparency' in img.info:
                    img = img.convert('RGBA')
                if img.mode in ('RGBA', 'LA'):
                    # Create black background for transparent images
                    background = Image.new('RGB', img.size, (0, 0, 0))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
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


def strip_exif_data(image_data: bytes) -> bytes:
    """
    Strip EXIF and other metadata from an image byte stream.
    
    This function creates a new image from the source data, dropping all
    metadata tags (EXIF, IPTC, XMP) which effectively anonymizes technical
    metadata that might contain PII (e.g., GPS, Patient Name in user comment).
    
    Args:
        image_data: Raw image data as bytes
        
    Returns:
        Cleaned image data as bytes. Returns original data if processing fails.
    """
    try:
        if not image_data:
            return image_data

        with BytesIO(image_data) as in_stream:
            with Image.open(in_stream) as img:
                data = list(img.getdata())
                # Create a new image without metadata
                clean_img = Image.new(img.mode, img.size)
                clean_img.putdata(data)
                
                # Copy format
                fmt = img.format or 'JPEG'
                
                with BytesIO() as out_stream:
                    # Save without extra metadata
                    clean_img.save(out_stream, format=fmt)
                    return out_stream.getvalue()
                    
    except Exception as e:
        logger.error(
            "Failed to strip EXIF data: %s",
            sanitize_log_value(e)
        )
        return image_data
