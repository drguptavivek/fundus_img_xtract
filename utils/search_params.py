"""Shared helpers for parsing search query parameters."""

from __future__ import annotations

from datetime import date as _date
from typing import Optional

from utils.date_utils import parse_date_yyyy_mm_dd


def parse_search_date(value: Optional[str]) -> Optional[_date]:
    """Parse YYYY-MM-DD search params into a date."""
    return parse_date_yyyy_mm_dd(value)


def parse_bool_param(value: Optional[str]) -> Optional[bool]:
    """Parse common truthy/falsey strings into a boolean."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    return None
