"""
S3 Input Validation and Sanitization

Security utilities for validating S3-related inputs to prevent:
- Path traversal attacks
- Invalid bucket names
- Malformed object keys
- Invalid encryption keys
"""

import re
import os
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

from utils.filename_sanitizer import sanitize_path_component, sanitize_storage_filename


class S3ValidationError(ValueError):
    """Raised when S3 input validation fails."""
    pass


def validate_s3_object_key(key: str, max_length: int = 500) -> str:
    """
    Validate and sanitize S3 object keys.

    Prevents:
    - Path traversal (../, ./, etc.)
    - Invalid characters
    - Overly long keys
    - Empty components

    Args:
        key: The S3 object key to validate
        max_length: Maximum allowed key length (S3 limit is 1024, we use 500)

    Returns:
        Sanitized S3 object key

    Raises:
        S3ValidationError: If validation fails

    Example:
        >>> validate_s3_object_key("uploads/2024/image.jpg")
        'uploads/2024/image.jpg'
        >>> validate_s3_object_key("../../../etc/passwd")
        Raises S3ValidationError
    """
    if not key or not key.strip():
        raise S3ValidationError("S3 object key cannot be empty")

    # Remove leading/trailing whitespace and slashes
    key = key.strip().strip('/')

    # Split by path separator
    parts = key.split('/')

    # Sanitize each component
    sanitized_parts = []
    for idx, part in enumerate(parts):
        if not part:
            continue  # Skip empty parts

        # Detect path traversal attempts
        if part in ('.', '..'):
            raise S3ValidationError(f"Path traversal detected in S3 key: {key}")

        # Sanitize component (last component treated as filename)
        try:
            if idx == len(parts) - 1:
                secured = sanitize_storage_filename(part, allow_no_ext=True)
            else:
                secured = sanitize_path_component(part)
        except ValueError as e:
            raise S3ValidationError(f"Invalid component in S3 key: {part}") from e

        sanitized_parts.append(secured)

    if not sanitized_parts:
        raise S3ValidationError("S3 object key resulted in empty path after sanitization")

    # Reconstruct the key
    sanitized_key = '/'.join(sanitized_parts)

    # Check length
    if len(sanitized_key) > max_length:
        raise S3ValidationError(f"S3 object key too long: {len(sanitized_key)} > {max_length}")

    return sanitized_key


def validate_bucket_name(name: str) -> str:
    """
    Validate S3 bucket name per AWS naming rules.

    Rules:
    - 3-63 characters long
    - Lowercase letters, numbers, hyphens only
    - Must start and end with letter or number
    - No consecutive periods or dashes
    - Not formatted as IP address

    Args:
        name: Bucket name to validate

    Returns:
        Validated bucket name (unchanged if valid)

    Raises:
        S3ValidationError: If validation fails

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
    """
    if not name or not name.strip():
        raise S3ValidationError("Bucket name cannot be empty")

    name = name.strip().lower()

    # Length check
    if not 3 <= len(name) <= 63:
        raise S3ValidationError(f"Bucket name must be 3-63 characters, got {len(name)}")

    # Format check (lowercase alphanumeric and hyphens)
    if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', name):
        raise S3ValidationError(
            "Bucket name must start/end with letter or number, "
            "and contain only lowercase letters, numbers, and hyphens"
        )

    # No consecutive hyphens
    if '--' in name:
        raise S3ValidationError("Bucket name cannot contain consecutive hyphens")

    # Not an IP address
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', name):
        raise S3ValidationError("Bucket name cannot be formatted as IP address")

    # Reserved prefixes
    if name.startswith('xn--'):
        raise S3ValidationError("Bucket name cannot start with 'xn--'")

    return name


def validate_s3_region(region: str) -> str:
    """
    Validate S3 region name.

    Supports:
    - AWS regions: us-east-1, eu-west-2, ap-southeast-1, etc.
    - Non-AWS providers: any alphanumeric string with hyphens/underscores

    Args:
        region: S3 region identifier

    Returns:
        Validated region (normalized to lowercase)

    Raises:
        S3ValidationError: If validation fails
    """
    if not region or not region.strip():
        raise S3ValidationError("Region cannot be empty")

    region = region.strip().lower()

    # Allow flexible region format for non-AWS providers
    # Supports: us-east-1, garage, eu, auto, us-east, etc.
    # Must be 1-64 chars, alphanumeric with hyphens/underscores
    if not re.match(r'^[a-z0-9_-]{1,64}$', region):
        raise S3ValidationError(
            f"Invalid region format: {region}. "
            "Use alphanumeric characters, hyphens, or underscores (max 64 chars)."
        )

    return region


def validate_endpoint_url(url: Optional[str]) -> Optional[str]:
    """
    Validate S3 endpoint URL (for MinIO, LocalStack, etc.).

    Args:
        url: Endpoint URL (optional)

    Returns:
        Validated URL or None

    Raises:
        S3ValidationError: If validation fails
    """
    if not url:
        return None

    url = url.strip()

    # Must be HTTP or HTTPS
    if not url.startswith(('http://', 'https://')):
        raise S3ValidationError("Endpoint URL must start with http:// or https://")

    # Basic URL validation
    if not re.match(r'^https?://[a-zA-Z0-9\-\.]+(:\d+)?(/.*)?$', url):
        raise S3ValidationError(f"Invalid endpoint URL format: {url}")

    # Warn about HTTP in production (allow for local dev)
    if url.startswith('http://') and not any(x in url for x in ['localhost', '127.0.0.1', '0.0.0.0']):
        # This is a warning, not an error - log it but allow
        import logging
        logger = logging.getLogger('security.s3')
        logger.warning(f"Non-HTTPS endpoint URL in use: {url}")

    return url


def validate_path_prefix(prefix: Optional[str], max_length: int = 255) -> Optional[str]:
    """
    Validate S3 path prefix (e.g., "fundus/prod/").

    Args:
        prefix: Path prefix (optional)
        max_length: Maximum allowed length

    Returns:
        Sanitized prefix with trailing slash, or None

    Raises:
        S3ValidationError: If validation fails
    """
    if not prefix:
        return None

    prefix = prefix.strip()

    # Empty after strip
    if not prefix:
        return None

    # Validate as object key
    prefix = validate_s3_object_key(prefix, max_length=max_length)

    # Ensure trailing slash
    if not prefix.endswith('/'):
        prefix += '/'

    return prefix


def validate_encryption_key(key: str) -> bytes:
    """
    Validate Fernet encryption key.

    Args:
        key: Base64-encoded Fernet key

    Returns:
        Validated key as bytes

    Raises:
        S3ValidationError: If validation fails
    """
    if not key or not key.strip():
        raise S3ValidationError("Encryption key cannot be empty")

    key = key.strip()

    # Try to create a Fernet instance (validates format)
    try:
        key_bytes = key.encode() if isinstance(key, str) else key
        Fernet(key_bytes)
        return key_bytes
    except (ValueError, InvalidToken) as e:
        raise S3ValidationError(f"Invalid Fernet encryption key: {e}")


def validate_s3_config_name(name: str, max_length: int = 100) -> str:
    """
    Validate S3 config name (user-friendly identifier).

    Args:
        name: Config name
        max_length: Maximum allowed length

    Returns:
        Validated name

    Raises:
        S3ValidationError: If validation fails
    """
    if not name or not name.strip():
        raise S3ValidationError("Config name cannot be empty")

    name = name.strip()

    # Length check
    if len(name) > max_length:
        raise S3ValidationError(f"Config name too long: {len(name)} > {max_length}")

    # Allow alphanumeric, spaces, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9\s\-_]+$', name):
        raise S3ValidationError(
            "Config name can only contain letters, numbers, spaces, hyphens, and underscores"
        )

    return name


def sanitize_for_s3_key(filename: str, prefix: str = "") -> str:
    """
    Convenience function: Sanitize a filename for use as S3 object key.

    Args:
        filename: Original filename
        prefix: Optional prefix (e.g., "uploads/2024/")

    Returns:
        Full S3 object key with sanitized components

    Example:
        >>> sanitize_for_s3_key("../../etc/passwd", "uploads/")
        'uploads/etc/passwd'  # Path traversal removed
    """
    if not filename:
        raise S3ValidationError(f"Filename sanitization resulted in empty name: {filename}")

    # Combine with prefix
    if prefix:
        prefix = validate_path_prefix(prefix) or ""
        full_key = f"{prefix}{filename}"
    else:
        full_key = filename

    return validate_s3_object_key(full_key)


# ============================================================================
# Provider Validation
# ============================================================================

# Valid S3-compatible storage providers
VALID_PROVIDERS = {
    "r2",        # Cloudflare R2
    "hetzner",   # Hetzner Storage Box
    "aws",       # Amazon S3
    "gcp",       # Google Cloud Storage
    "azure",     # Azure Blob Storage
    "minio",     # MinIO
    "other",     # Other S3-compatible
}


def validate_provider(provider: str) -> bool:
    """
    Validate S3 provider name.

    Args:
        provider: Provider identifier

    Returns:
        True if provider is valid, False otherwise

    Example:
        >>> validate_provider("r2")
        True
        >>> validate_provider("invalid")
        False
    """
    if not provider:
        return False
    return provider.lower() in VALID_PROVIDERS


def validate_fallback_policy(policy: str) -> bool:
    """
    Validate S3 fallback policy.

    Args:
        policy: Policy identifier ("never" or "always")

    Returns:
        True if policy is valid, False otherwise
    """
    if not policy:
        return False
    return policy.lower() in {"never", "always"}


# Note: S3 encryption now uses PyNaCl (via utils/s3_encryption_nacl.py)
# Master key from S3_ENCRYPTION_KEY environment variable
# Hospital-specific keys derived via Argon2id KDF
