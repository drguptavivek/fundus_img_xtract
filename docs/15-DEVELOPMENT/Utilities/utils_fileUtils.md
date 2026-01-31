# File Utilities Documentation

This document provides an overview of the utility functions available in the file utilities module. These utilities are designed to handle file operations including path validation, security checks, and file serving.

## Functions

### `_safe_file(base_dir: Path, filename: str) -> tuple[str, str]`

Prevent path traversal & ensure file exists inside base_dir.
Returns (directory_str, filename_str) for send_from_directory.

**Parameters:**
- `base_dir` (Path): The base directory where the file should exist
- `filename` (str): The filename to validate

**Returns:**
- `tuple[str, str]`: A tuple containing the directory path and filename for use with Flask's send_from_directory function

**Implementation Details:**
- Uses secure_filename to strip any path parts that could lead to path traversal
- Uses os.path.basename to extract only the filename
- Aborts with 404 if the file doesn't exist or isn't a file

### `_ensure_under_root(abs_path: Path, root: Path) -> None`

Ensure abs_path is inside root (prevents traversal / wrong volume).

**Parameters:**
- `abs_path` (Path): The absolute path to check
- `root` (Path): The root path that abs_path should be under

**Implementation Details:**
- Resolves both paths to absolute paths
- Uses relative_to to verify that abs_path is under root
- Aborts with 404 if the path is outside the root directory

### `_send_file_with_headers(abs_path: Path, mimetype: str | None = None) -> Response`

Cross-platform safe file send with sensible headers.

**Parameters:**
- `abs_path` (Path): The absolute path of the file to send
- `mimetype` (str | None): Optional mimetype; if not provided, it will be guessed

**Returns:**
- `Response`: Flask response with the file and appropriate headers

**Implementation Details:**
- Resolves the path to an absolute path
- Aborts with 404 if the file doesn't exist or isn't a file
- Guesses the mimetype if not provided
- Sets security headers like "X-Content-Type-Options" and "Cache-Control"
- Enables conditional requests with "If-Modified-Since"

### `ensure_root() -> Path`

Ensure the DIRECT_UPLOAD_DIR exists and return it.

**Returns:**
- `Path`: The direct upload directory path

**Implementation Details:**
- Creates the directory if it doesn't exist (with parents)
- Returns the DIRECT_UPLOAD_DIR constant

### `_is_inside(child: Path, root: Path) -> bool`

Check if a path is inside another path.

**Parameters:**
- `child` (Path): The child path to check
- `root` (Path): The root path that child should be inside

**Returns:**
- `bool`: True if child is inside root, False otherwise

**Implementation Details:**
- Uses Path.is_relative_to for Python 3.9+ (if available)
- Falls back to string comparison for older Python versions

### `relfolder(folder: Path) -> str`

POSIX-style directory path relative to BASE_DIR for DB storage.
Safe if a file path is passed — its parent folder is used.

**Parameters:**
- `folder` (Path): The path to convert to a relative path

**Returns:**
- `str`: POSIX-style relative path as a string

**Implementation Details:**
- If a file path is passed, uses the parent directory
- Computes the relative path to BASE_DIR
- Returns the path in POSIX format using as_posix()

### `abs_from_parts(folder_rel: str, filename: str, kind: str = "orig") -> Path`

Resolve absolute path under DIRECT_UPLOAD_DIR.

**Parameters:**
- `folder_rel` (str): The relative folder name (e.g. '2025_09_01_user7' from DB)
- `filename` (str): The filename (basename only, e.g. 'foo.jpg')
- `kind` (str): The file kind ('orig', 'edited', or 'dup') - defaults to 'orig'

**Returns:**
- `Path`: The resolved absolute path

**Implementation Details:**
- Validates that folder_rel and filename don't contain path separators
- Creates paths based on the kind parameter:
  - 'orig': base folder
  - 'edited': base folder / 'edited' subfolder
  - 'dup': base folder / 'dup' subfolder
- Performs security check to ensure path is inside DIRECT_UPLOAD_DIR

### `get_upload_dirs(user_id: int, when: Optional[datetime] = None) -> tuple[Path, Path, Path, str]`

Create/return directories for this user/day.

**Parameters:**
- `user_id` (int): The ID of the user
- `when` (Optional[datetime]): The date to use; defaults to current UTC time

**Returns:**
- `tuple[Path, Path, Path, str]`: A tuple containing:
  - `orig_dir`: The original file directory
  - `edited_dir`: The edited file directory
  - `dup_dir`: The duplicate file directory
  - `folder_rel`: String for DB storage (e.g. '2025_09_01_user7')

**Implementation Details:**
- Creates directory structure based on the date and user ID
- Creates all required subdirectories (orig, edited, dup)
- Uses the current UTC time if no 'when' parameter is provided
- Folder names follow the format 'YYYY_MM_DD_user{ID}'