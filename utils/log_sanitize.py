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


def mask_email(email: str | None) -> str:
    """Mask email address for logging (e.g. 'jo***@example.com')."""
    if not email:
        return ""
    s_email = str(email)
    if "@" not in s_email:
        return sanitize_log_value(s_email)
    
    parts = s_email.split("@")
    if len(parts) != 2:
        return sanitize_log_value(s_email)
        
    local, domain = parts
    if len(local) <= 2:
        return f"***@{domain}"
    
    return f"{local[:2]}***@{domain}"


def mask_pii(value: str | None) -> str:
    """Generic PII masking (e.g. for phone numbers or names)."""
    if not value:
        return ""
    s_value = str(value)
    if len(s_value) <= 4:
        return "***"
    return f"{s_value[:2]}***{s_value[-2:]}"
