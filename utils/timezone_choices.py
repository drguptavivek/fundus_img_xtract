"""Timezone option helpers backed by Python's zoneinfo."""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List, Tuple

from zoneinfo import available_timezones

DEFAULT_TIMEZONE = "Asia/Kolkata"


def _humanize_timezone(tz: str) -> str:
    """Create a human-readable label from a timezone identifier."""
    if tz.upper() == "UTC":
        return "Coordinated Universal Time (UTC)"
    parts = tz.split("/")
    if len(parts) == 1:
        return tz.replace("_", " ")
    region = parts[0].replace("_", " ")
    city = parts[-1].replace("_", " ")
    return f"{city} ({region})"


@lru_cache(maxsize=1)
def _build_choices() -> List[Tuple[str, str]]:
    timezones: Iterable[str] = available_timezones()
    choices: List[Tuple[str, str]] = []
    for tz in sorted(timezones):
        label = _humanize_timezone(tz)
        choices.append((tz, label))

    # Ensure the default timezone is always present (even if environment lacks it)
    if DEFAULT_TIMEZONE not in {tz for tz, _ in choices}:
        choices.insert(0, (DEFAULT_TIMEZONE, _humanize_timezone(DEFAULT_TIMEZONE)))

    return choices


TIMEZONE_CHOICES: List[Tuple[str, str]] = _build_choices()
TIMEZONE_VALUES = {tz for tz, _ in TIMEZONE_CHOICES}
TIMEZONE_LABELS = {tz: label for tz, label in TIMEZONE_CHOICES}

__all__ = [
    "TIMEZONE_CHOICES",
    "TIMEZONE_VALUES",
    "DEFAULT_TIMEZONE",
    "TIMEZONE_LABELS",
]
