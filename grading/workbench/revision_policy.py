"""Shared grading revision-window policy."""

from datetime import timedelta


REVISION_WINDOW_HOURS = 12
REVISION_WINDOW = timedelta(hours=REVISION_WINDOW_HOURS)
