"""Log sanitization helpers for untrusted values."""

from __future__ import annotations


def sanitize_log_value(value: object, max_len: int = 100) -> str:
    """
    Return a safe, single-line string for logging.

    Sanitizes the input by:
    - Stripping null bytes (injection attack prevention)
    - Replacing newlines/carriage returns with escape sequences
    - Limiting length to max_len characters

    Args:
        value: The value to sanitize
        max_len: Maximum length of returned string

    Returns:
        Sanitized string safe for logging
    """
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)

    # SECURITY: Strip null bytes to prevent injection attacks
    text = text.replace("\x00", "")

    # Replace newlines/carriage returns with escape sequences
    text = text.replace("\r", "\\r").replace("\n", "\\n")

    # Limit length
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


def mask_text_emails(text: str | None) -> str:
    """Mask email addresses within a larger text block (no length limit)."""
    if not text:
        return ""
    s_text = str(text)
    

    # Simple regex for email-like patterns
    import re
    email_pattern = r'\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b'
    
    def replace_email(match):
        local, domain = match.groups()
        if len(local) <= 2:
            return f"***@{domain}"
        return f"{local[:2]}***@{domain}"
        
    return re.sub(email_pattern, replace_email, s_text)
