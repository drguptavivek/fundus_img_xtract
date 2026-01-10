"""Log sanitization helpers for untrusted values."""

from __future__ import annotations


def sanitize_log_value(value: object, max_len: int = 100) -> str:
    """Return a safe, single-line string for logging."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    if len(text) > max_len:
        return text[:max_len]
    return text
