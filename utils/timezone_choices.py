"""Common timezone options for user preferences."""
from __future__ import annotations

from typing import List, Tuple

TIMEZONE_CHOICES: List[Tuple[str, str]] = [
    ("Asia/Kolkata", "India Standard Time (Asia/Kolkata)"),
    ("UTC", "Coordinated Universal Time (UTC)"),
    ("Asia/Dubai", "Gulf Standard Time (Asia/Dubai)"),
    ("Asia/Singapore", "Singapore Time (Asia/Singapore)"),
    ("Asia/Tokyo", "Japan Standard Time (Asia/Tokyo)"),
    ("Europe/London", "Greenwich Mean Time (Europe/London)"),
    ("Europe/Berlin", "Central European Time (Europe/Berlin)"),
    ("America/New_York", "Eastern Time (America/New_York)"),
    ("America/Chicago", "Central Time (America/Chicago)"),
    ("America/Los_Angeles", "Pacific Time (America/Los_Angeles)"),
    ("Australia/Sydney", "Australian Eastern Time (Australia/Sydney)"),
]

TIMEZONE_VALUES = {tz for tz, _ in TIMEZONE_CHOICES}
DEFAULT_TIMEZONE = "Asia/Kolkata"
TIMEZONE_LABELS = {tz: label for tz, label in TIMEZONE_CHOICES}

__all__ = [
    "TIMEZONE_CHOICES",
    "TIMEZONE_VALUES",
    "DEFAULT_TIMEZONE",
    "TIMEZONE_LABELS",
]
