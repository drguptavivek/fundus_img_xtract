# Datetime Filters Utilities Documentation

This document provides an overview of the utility functions available in the datetime filters module. These utilities are designed for timezone-aware datetime rendering in Jinja templates.

## Module Overview

This module provides Jinja filters for timezone-aware datetime rendering, designed to format UTC datetimes for display in the user's preferred timezone.

## Constants

### `DEFAULT_DISPLAY_TIMEZONE`

The default timezone used when no user timezone is set or when configuration is missing.

## Functions

### `_resolve_target_timezone() -> ZoneInfo`

Resolve the preferred timezone for the active request.

**Returns:**
- `ZoneInfo`: The timezone to be used for displaying dates and times

**Implementation Details:**
- First tries to get the timezone from the current user's settings
- Falls back to configuration options (DEFAULT_DISPLAY_TIMEZONE, then TIMEZONE)
- Finally falls back to the DEFAULT_DISPLAY_TIMEZONE constant
- If an invalid timezone name is provided, logs a warning and falls back to DEFAULT_DISPLAY_TIMEZONE

### `_ensure_aware(value: datetime) -> datetime`

Ensure the datetime is timezone-aware, assuming UTC when naive.

**Parameters:**
- `value` (datetime): The datetime to check and potentially make timezone-aware

**Returns:**
- `datetime`: A timezone-aware datetime object

**Implementation Details:**
- If the datetime has no timezone information (naive), it assumes it's in UTC
- If the datetime already has timezone information, it returns it as is

### `format_user_datetime(value: Optional[datetime | date], fmt: str = "%Y-%m-%d %H:%M") -> str`

Format a UTC datetime for display in the user's timezone.

**Parameters:**
- `value` (Optional[datetime | date]): The datetime to format (expected to be UTC in storage)
- `fmt` (str): strftime-style formatting string, defaults to "%Y-%m-%d %H:%M"

**Returns:**
- `str`: The formatted datetime string, or an empty string when no value is provided

**Implementation Details:**
- If a date (without time) is provided, it converts it to a datetime at midnight UTC
- Ensures the datetime is timezone-aware using `_ensure_aware`
- Resolves the target timezone using `_resolve_target_timezone`
- Converts the datetime from UTC to the target timezone
- Formats the localized datetime using the provided format string
- Includes defensive error handling with fallback formatting

## Module Constants

### `__all__`

List of public module members: ['format_user_datetime']