# Timezone Choices Utilities Documentation

This document provides an overview of the utility functions available in the timezone choices module. These utilities are designed for providing timezone options backed by Python's zoneinfo module.

## Module Overview

This module provides helpers for timezone selection, including human-readable labels for timezone identifiers and a list of valid timezone choices for use in forms or other UI elements.

## Constants

### `DEFAULT_TIMEZONE`

The default timezone used in the application, retrieved from the environment variable DEFAULT_DISPLAY_TIMEZONE, with a fallback to "Asia/Kolkata".

### `TIMEZONE_CHOICES`

A list of tuples containing (timezone identifier, human-readable label) pairs, suitable for use in form fields or dropdowns.

### `TIMEZONE_VALUES`

A set of valid timezone identifiers that can be used for validation purposes.

### `TIMEZONE_LABELS`

A dictionary mapping timezone identifiers to their human-readable labels.

## Functions

### `_humanize_timezone(tz: str) -> str`

Create a human-readable label from a timezone identifier.

**Parameters:**
- `tz` (str): The timezone identifier (e.g., "America/New_York")

**Returns:**
- `str`: A human-readable label for the timezone

**Implementation Details:**
- For "UTC", returns "Coordinated Universal Time (UTC)"
- For other timezones, splits the identifier by "/" and formats as "{city} ({region})"
- Replaces underscores with spaces for better readability
- Handles both single-part identifiers (like "UTC") and multi-part ones (like "America/New_York")

### `_build_choices() -> List[Tuple[str, str]]`

Build the list of timezone choices by processing all available timezones from zoneinfo.

**Returns:**
- `List[Tuple[str, str]]`: A list of (timezone identifier, human-readable label) tuples

**Implementation Details:**
- Uses lru_cache to cache the result for performance
- Gets all available timezones from zoneinfo.available_timezones()
- Sorts the timezones alphabetically
- Creates human-readable labels using _humanize_timezone
- Ensures the DEFAULT_TIMEZONE is always included in the choices, even if the environment doesn't have it
- Returns the sorted list of choices

## Module Constants

### `__all__`

List of public module members: ["TIMEZONE_CHOICES", "TIMEZONE_VALUES", "DEFAULT_TIMEZONE", "TIMEZONE_LABELS"]