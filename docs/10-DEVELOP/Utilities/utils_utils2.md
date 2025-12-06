# Additional Utilities Documentation

This document provides an overview of the additional utility functions available in the utils2 module. This module contains miscellaneous helper functions that don't fit in other utility modules.

## Module Overview

This module provides various utility functions for file handling, data validation, and general helper operations in the fundus image manager application.

## Functions

### `calculate_file_hash(filepath: Union[str, Path]) -> str`

Calculate MD5 hash of a file.

**Parameters:**
- `filepath` (Union[str, Path]): Path to the file to hash

**Returns:**
- `str`: MD5 hash of the file as a hexadecimal string

**Implementation Details:**
- Reads the file in 4KB chunks to efficiently handle large files
- Uses MD5 algorithm to calculate the hash
- Returns the hash as a hexadecimal string

### `format_file_size(size_bytes: int) -> str`

Format file size in human-readable format.

**Parameters:**
- `size_bytes` (int): File size in bytes

**Returns:**
- `str`: Formatted file size with appropriate units (B, KB, MB, GB, TB)

**Implementation Details:**
- Returns "0 B" for zero-byte files
- Converts bytes to larger units (KB, MB, GB, TB) as needed
- Uses 1024 as the conversion factor between units
- Formats the result to one decimal place

### `sanitize_filename(filename: str) -> str`

Sanitize filename to prevent path traversal and other issues.

**Parameters:**
- `filename` (str): Filename to sanitize

**Returns:**
- `str`: Sanitized filename

**Implementation Details:**
- Removes path components using os.path.basename()
- Replaces potentially dangerous characters (< > : " / \\ | ? *) with underscores
- Limits filename length to 255 characters
- Preserves file extension during length limiting

### `uniquify(dest_dir: Path, filename: str) -> Path`

Create a unique filename by adding a numeric suffix if needed.

**Parameters:**
- `dest_dir` (Path): Destination directory for the file
- `filename` (str): Original filename

**Returns:**
- `Path`: Path object with a unique filename

**Implementation Details:**
- Checks if the file already exists in the destination directory
- If it exists, adds a numeric suffix (e.g., "__1") before the extension
- Increments the suffix until a unique filename is found

### `get_file_extension(filename: str) -> str`

Get file extension in lowercase.

**Parameters:**
- `filename` (str): Filename to extract extension from

**Returns:**
- `str`: File extension in lowercase with the leading dot

### `is_allowed_file_extension(filename: str, allowed_extensions: set) -> bool`

Check if file extension is in allowed extensions set.

**Parameters:**
- `filename` (str): Filename to check
- `allowed_extensions` (set): Set of allowed file extensions

**Returns:**
- `bool`: True if the file extension is allowed, False otherwise

### `get_current_timestamp() -> str`

Get current timestamp in ISO format.

**Returns:**
- `str`: Current timestamp in ISO format (UTC)

**Implementation Details:**
- Returns timestamp in ISO 8601 format with timezone information (UTC)

### `safe_int(value: Any, default: int = 0) -> int`

Safely convert value to int.

**Parameters:**
- `value` (Any): Value to convert to int
- `default` (int): Default value if conversion fails, defaults to 0

**Returns:**
- `int`: Converted integer or default value

**Implementation Details:**
- Handles TypeError and ValueError exceptions during conversion
- Returns the default value if conversion fails

### `safe_float(value: Any, default: float = 0.0) -> float`

Safely convert value to float.

**Parameters:**
- `value` (Any): Value to convert to float
- `default` (float): Default value if conversion fails, defaults to 0.0

**Returns:**
- `float`: Converted float or default value

**Implementation Details:**
- Handles TypeError and ValueError exceptions during conversion
- Returns the default value if conversion fails

### `is_valid_uuid(uuid_string: str) -> bool`

Check if string is a valid UUID format.

**Parameters:**
- `uuid_string` (str): String to check for UUID format

**Returns:**
- `bool`: True if the string matches UUID format, False otherwise

**Implementation Details:**
- Uses regular expression to validate the UUID format
- Checks for the standard UUID format: 8-4-4-4-12 hex characters separated by hyphens

### `get_directory_size(path: Union[str, Path]) -> int`

Calculate total size of directory in bytes.

**Parameters:**
- `path` (Union[str, Path]): Path to the directory to calculate size for

**Returns:**
- `int`: Total size of directory in bytes

**Implementation Details:**
- Recursively walks through all subdirectories and files
- Adds up the size of all files
- Handles potential file access errors gracefully by skipping problematic files