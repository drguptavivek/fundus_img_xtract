"""Jinja filters for timezone-aware datetime rendering."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask import current_app
from flask_login import current_user
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_DISPLAY_TIMEZONE = "Asia/Kolkata"


def _resolve_target_timezone() -> ZoneInfo:
    """Resolve the preferred timezone for the active request."""
    tz_name: Optional[str] = None

    try:
        tz_name = getattr(current_user, "timezone", None)
    except Exception:
        tz_name = None

    if not tz_name:
        tz_name = (current_app.config.get("DEFAULT_DISPLAY_TIMEZONE")
                   or current_app.config.get("TIMEZONE")
                   or DEFAULT_DISPLAY_TIMEZONE)

    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        current_app.logger.warning("Unknown timezone '%s', falling back to %s", tz_name, DEFAULT_DISPLAY_TIMEZONE)
        return ZoneInfo(DEFAULT_DISPLAY_TIMEZONE)


def _ensure_aware(value: datetime) -> datetime:
    """Ensure the datetime is timezone-aware, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def format_user_datetime(value: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Format a UTC datetime for display in the user's timezone.

    Args:
        value: The datetime to format (expected to be UTC in storage).
        fmt:   strftime-style formatting string.

    Returns:
        The formatted datetime string, or an empty string when no value is provided.
    """
    if value is None:
        return ""

    try:
        aware_value = _ensure_aware(value)
        target_tz = _resolve_target_timezone()
        localized = aware_value.astimezone(target_tz)
        return localized.strftime(fmt)
    except Exception as exc:  # pragma: no cover - defensive fallback
        current_app.logger.error("Failed to format datetime: %s", exc)
        try:
            return value.strftime(fmt)
        except Exception:
            return ""


__all__ = ["format_user_datetime"]
