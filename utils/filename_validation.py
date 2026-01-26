"""
Secure filename validation utilities for file uploads.

This module provides strict validation for uploaded filenames to prevent:
- Path traversal attacks (CWE-434)
- Null byte injection
- Log injection attempts
- Invalid UTF-8 encoding
- Special character injection
"""

import re
import logging

# Regex pattern for safe file extensions
# Allows: alphanumeric only, 2-10 chars
EXTENSION_PATTERN = re.compile(r'^[a-zA-Z0-9]{2,10}$')

# Maximum filename length
MAX_FILENAME_LENGTH = 255

# Path traversal patterns to detect
PATH_TRAVERSAL_PATTERNS = [
    r'\.\.[/\\]',  # Parent directory with separator (illegal)
    r'~/',  # Home directory
    r'%2e%2e',  # URL-encoded parent directory (case-insensitive)
    r'\x00',  # Null byte
]

# Combined pattern for detecting path traversal
PATH_TRAVERSAL_REGEX = re.compile(
    '|'.join(PATH_TRAVERSAL_PATTERNS),
    re.IGNORECASE
)

logger = logging.getLogger('security.filename_validation')


def validate_upload_filename(filename: str) -> tuple[bool, str]:
    """
    Validate an uploaded filename for security.

    This function performs strict validation to prevent path traversal,
    null byte injection, and other filename-based attacks.

    Args:
        filename: The filename to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if filename is valid, False otherwise
        - error_message: Error description if invalid, empty string if valid

    Security checks:
        1. Null byte detection and rejection
        2. Path traversal pattern detection
        3. Special character validation
        4. Filename length limit
        5. Extension requirement
        6. UTF-8 encoding validation

    Examples:
        >>> validate_upload_filename("image.jpg")
        (True, "")

        >>> validate_upload_filename("../etc/passwd")
        (False, "Path traversal detected")

        >>> validate_upload_filename("test\x00file.jpg")
        (False, "Null bytes detected")
    """
    if not filename:
        return False, "Filename is empty"

    # Check 1: Null byte detection (CRITICAL - must be first)
    if '\x00' in filename:
        logger.warning("Null byte detected in filename: %r", filename)
        return False, "Null bytes detected in filename"

    # Check 2: Filename length limit
    if len(filename) > MAX_FILENAME_LENGTH:
        logger.warning("Filename too long: %d characters", len(filename))
        return False, f"Filename exceeds maximum length of {MAX_FILENAME_LENGTH} characters"

    # Check 3: Empty filename (whitespace only)
    if not filename.strip():
        return False, "Filename is empty or whitespace only"

    # Check 4: Path traversal patterns (CRITICAL)
    if PATH_TRAVERSAL_REGEX.search(filename):
        logger.warning("Path traversal pattern detected in filename: %r", filename)
        return False, "Path traversal patterns detected in filename"

    # Check 5: UTF-8 validation
    is_utf8, utf8_error = validate_utf8(filename)
    if not is_utf8:
        return False, utf8_error

    # Check 6: Control characters (disallow)
    if any(ord(ch) < 32 for ch in filename):
        logger.warning("Control characters detected in filename: %r", filename)
        return False, "Filename contains invalid control characters"

    # Check 7: Allowed characters (Unicode alnum + safe separators)
    allowed_punct = {".", "_", "-", " ", "(", ")", "[", "]", ",", "/", "\\", ":"}
    if any(not (ch.isalnum() or ch in allowed_punct) for ch in filename):
        logger.warning("Invalid characters in filename: %r", filename)
        return False, "Filename contains invalid characters"

    # Check 8: Extension validation (required)
    if '.' not in filename:
        logger.warning("Filename missing extension: %r", filename)
        return False, "Filename must include a file extension"

    base, ext = filename.rsplit('.', 1)
    if not base.strip():
        logger.warning("Filename missing base name: %r", filename)
        return False, "Filename must include a base name"

    if not EXTENSION_PATTERN.match(ext):
        logger.warning("Invalid file extension: %r", ext)
        return False, "File extension must be 2-10 alphanumeric characters"

    return True, ""


def sanitize_filename_for_logging(filename: str) -> str:
    """
    Sanitize a filename for safe logging.

    Removes null bytes and replaces dangerous characters
    with safe alternatives.

    Args:
        filename: The filename to sanitize

    Returns:
        Sanitized filename safe for logging

    Examples:
        >>> sanitize_filename_for_logging("test\x00file.jpg")
        "test_file.jpg"

        >>> sanitize_filename_for_logging("../etc/passwd")
        ".._etc_passwd"
    """
    if not filename:
        return ""

    # Remove null bytes
    sanitized = filename.replace('\x00', '_')

    # Replace path separators with underscores
    sanitized = sanitized.replace('/', '_').replace('\\', '_')

    # Replace other potentially dangerous characters
    sanitized = sanitized.replace('<', '_').replace('>', '_')
    sanitized = sanitized.replace('|', '_').replace(';', '_')
    sanitized = sanitized.replace('&', '_').replace('$', '_')

    # Limit length for logging
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + '...'

    return sanitized


def strip_null_bytes(value: str) -> str:
    """
    Strip null bytes from a string.

    Null bytes can be used for injection attacks and should
    be removed from all user input.

    Args:
        value: The string to strip null bytes from

    Returns:
        String with null bytes removed
    """
    if not value:
        return value
    return value.replace('\x00', '')


def validate_utf8(value: str) -> tuple[bool, str]:
    """
    Validate that a string is valid UTF-8.

    Args:
        value: The string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value:
        return True, ""

    try:
        # Try to encode and decode as UTF-8
        value.encode('utf-8').decode('utf-8')
        return True, ""
    except (UnicodeEncodeError, UnicodeDecodeError) as e:
        logger.warning("Invalid UTF-8 detected: %s", str(e))
        return False, f"Invalid UTF-8 encoding: {str(e)}"
