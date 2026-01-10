"""Shared date parsing utilities."""

from __future__ import annotations

from datetime import date as _date, datetime


def parse_date_yyyy_mm_dd(value: str | None) -> _date | None:
    """Parse YYYY-MM-DD into a date, returning None for empty/invalid values."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
