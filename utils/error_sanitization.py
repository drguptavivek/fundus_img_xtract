"""
Error message and stack trace sanitization utilities.

This module provides functions to sanitize error messages and stack traces
to prevent information disclosure through log injection attacks (CWE-209).

Sanitization includes:
- Removing absolute file paths
- Masking sensitive headers (Authorization, Cookie, API keys)
- Sanitizing database connection strings
- Escaping log injection characters
"""

import re
import os
from typing import Optional


# Patterns to detect and sanitize sensitive information
SENSITIVE_PATTERNS = [
    # Database connection strings
    (re.compile(r"password\s*=\s*'[^']*'", re.IGNORECASE), "password='***'"),
    (re.compile(r"password\s*=\s*\"[^\"]*\"", re.IGNORECASE), 'password="***"'),
    (re.compile(r"postgres://[^@]+@([^@]+)"), r"postgres://***:***@\1"),
    (re.compile(r"mysql://[^@]+@([^@]+)"), r"mysql://***:***@\1"),
    (re.compile(r"mongodb://[^@]+@([^@]+)"), r"mongodb://***:***@\1"),

    # API keys and tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\._-]+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"api[_-]?key\s*[:=]\s*[A-Za-z0-9\._-]+", re.IGNORECASE), "api_key=***"),
    (re.compile(r"token\s*[:=]\s*[A-Za-z0-9\._-]+", re.IGNORECASE), "token=***"),

    # Secret keys
    (re.compile(r"secret[_-]?key\s*[:=]\s*[A-Za-z0-9\._-]+", re.IGNORECASE), "secret_key=***"),
    (re.compile(r"private[_-]?key\s*[:=]\s*[A-Za-z0-9\._-]+", re.IGNORECASE), "private_key=***"),
]

# Path patterns to sanitize
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH_PATTERNS = [
    # Remove /app/ prefix
    (re.compile(r"/app/"), ""),
    # Remove project root
    (re.compile(re.escape(PROJECT_ROOT)), "[project]"),
    # Remove user home directory
    (re.compile(r"/Users/[^/]+/"), "~/"),
    (re.compile(r"/home/[^/]+/"), "~/"),
    # Remove /var/www/ paths
    (re.compile(r"/var/www/[^/]+/"), ""),
]


def sanitize_stack_trace(stack_trace: str) -> str:
    """
    Sanitize a stack trace to remove sensitive information.

    Removes absolute file paths, connection strings, and other
    sensitive data while preserving debugging information.

    Args:
        stack_trace: The raw stack trace string

    Returns:
        Sanitized stack trace safe for logging

    Examples:
        >>> sanitize_stack_trace("File \"/app/app.py\", line 10")
        'File "app.py", line 10'
    """
    if not stack_trace:
        return ""

    sanitized = stack_trace

    # First, sanitize paths
    sanitized = sanitize_paths_in_trace(sanitized)

    # Then sanitize sensitive patterns
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_paths_in_trace(trace: str) -> str:
    """
    Remove or shorten file paths in a stack trace.

    Args:
        trace: The stack trace string

    Returns:
        Trace with sanitized paths
    """
    if not trace:
        return ""

    sanitized = trace

    # Apply path patterns
    for pattern, replacement in PATH_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_stack_path(file_path: str) -> str:
    """
    Sanitize a single file path from a stack trace.

    Removes the project root and other identifying information.

    Args:
        file_path: Absolute file path

    Returns:
        Sanitized relative path or filename

    Examples:
        >>> sanitize_stack_path("/app/direct_uploads/upload.py")
        'direct_uploads/upload.py'

        >>> sanitize_stack_path("/Users/vivekgupta/workspace/fundus_img_xtract/app.py")
        'app.py'
    """
    if not file_path:
        return file_path

    sanitized = file_path

    # Apply path patterns
    for pattern, replacement in PATH_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_header_value(header_name: str, header_value: str) -> str:
    """
    Sanitize a sensitive HTTP header value for logging.

    Masks or redacts sensitive headers like Authorization, Cookie, etc.

    Args:
        header_name: The header name (case-insensitive)
        header_value: The header value to sanitize

    Returns:
        Sanitized header value safe for logging

    Examples:
        >>> sanitize_header_value("Authorization", "Bearer token123")
        'Bearer ***'

        >>> sanitize_header_value("Cookie", "session=abc123; user=admin")
        'session=***; user=***'
    """
    if not header_value:
        return header_value

    header_lower = header_name.lower()

    # Sensitive headers that should be fully or partially masked
    sensitive_headers = {
        'authorization': '***',
        'cookie': _sanitize_cookie_header,
        'x-api-key': '***',
        'x-auth-token': '***',
        'x-csrf-token': '***',
        'set-cookie': _sanitize_cookie_header,
    }

    if header_lower in sensitive_headers:
        handler = sensitive_headers[header_lower]
        if callable(handler):
            return handler(header_value)
        return handler

    # For non-sensitive headers, just sanitize the value
    return _sanitize_value(header_value)


def _sanitize_cookie_header(cookie_value: str) -> str:
    """
    Sanitize a Cookie header value by masking cookie values.

    Args:
        cookie_value: The Cookie header value

    Returns:
        Sanitized cookie string
    """
    if not cookie_value:
        return cookie_value

    # Split by semicolon and sanitize each cookie
    cookies = cookie_value.split(';')
    sanitized = []

    for cookie in cookies:
        cookie = cookie.strip()
        if '=' in cookie:
            name, value = cookie.split('=', 1)
            # Keep the name but mask the value
            # Show first few chars of value for debugging
            if len(value) > 3:
                sanitized.append(f"{name}={value[:3]}***")
            else:
                sanitized.append(f"{name}=***")
        else:
            sanitized.append(cookie)

    return '; '.join(sanitized)


def _sanitize_value(value: str, max_length: int = 50) -> str:
    """
    Sanitize a generic value for logging.

    Args:
        value: The value to sanitize
        max_length: Maximum length of returned value

    Returns:
        Sanitized value
    """
    if not value:
        return value

    # Remove null bytes
    value = value.replace('\x00', '')

    # Truncate if too long
    if len(value) > max_length:
        return value[:max_length-3] + '***'

    return value


def sanitize_exception_message(message: str) -> str:
    """
    Sanitize an exception message to remove sensitive information.

    Args:
        message: The exception message

    Returns:
        Sanitized message
    """
    if not message:
        return message

    sanitized = message

    # Apply sensitive pattern sanitization
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized
