from datetime import datetime, timezone
import mimetypes
import os
from pathlib import Path
from typing import Optional
from flask import Response, abort, send_file
from werkzeug.utils import secure_filename
from models import ALLOWED_IMAGE_EXT, BASE_DIR, DIRECT_UPLOAD_DIR, IMAGE_DIR, PDF_DIR, Session, EncounterFile, PatientEncounters, ZipFile
from utils.image_processing import get_thumbnail_filename

 
def _safe_file(base_dir: Path, filename: str) -> tuple[str, str]:
    """
    Prevent path traversal & ensure file exists inside base_dir.
    Returns (directory_str, filename_str) for send_from_directory.
    """
    # Strip any path parts the client may try to sneak in
    fname = secure_filename(os.path.basename(filename))
    full = base_dir / fname
    if not full.exists() or not full.is_file():
        abort(404)
    return (str(base_dir), fname)

def _ensure_under_root(abs_path: Path, root: Path) -> None:
    """Ensure abs_path is inside root (prevents traversal / wrong volume)."""
    abs_path = abs_path.resolve()
    root = root.resolve()
    try:
        abs_path.relative_to(root)
    except Exception:
        abort(404)

def _send_file_with_headers(abs_path: Path, mimetype: str | None = None) -> Response:
    """Cross-platform safe file send with sensible headers."""
    abs_path = abs_path.resolve()
    if not abs_path.exists() or not abs_path.is_file():
        abort(404)

    # Guess type if not provided
    guessed, _ = mimetypes.guess_type(abs_path.name)
    mt = mimetype or guessed or "application/octet-stream"

    resp: Response = send_file(
        abs_path,
        mimetype=mt,
        as_attachment=False,
        conditional=True,   # enables range/If-Modified-Since
        etag=True,
        last_modified=abs_path.stat().st_mtime
    )
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Cache-Control", "private, max-age=600")
    return resp

def ensure_root() -> Path:
    DIRECT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return DIRECT_UPLOAD_DIR

def _is_inside(child: Path, root: Path) -> bool:
    try:
        return child.is_relative_to(root)  # py3.9+
    except AttributeError:
        return str(child).startswith(str(root))

def relfolder(folder: Path) -> str:
    """
    POSIX-style *directory* path relative to BASE_DIR for DB storage.
    Safe if a file path is passed — its parent folder is used.
    """
    d = folder if folder.is_dir() else folder.parent
    return d.relative_to(BASE_DIR).as_posix()

def abs_from_parts(folder_rel: str, filename: str, kind: str = "orig") -> Path:
    """
    Resolve absolute path under DIRECT_UPLOAD_DIR:
      - folder_rel: e.g. '2025_09_01_user7'  (DB value)
      - filename:   basename only, e.g. 'foo.jpg'
      - kind:       'orig' | 'edited' | 'dup'
    
    Returns absolute Path. Ensures it's inside DIRECT_UPLOAD_DIR.
    """
    if not folder_rel or "/" in folder_rel or "\\" in folder_rel:
        raise ValueError(f"Invalid folder_rel: {folder_rel!r}")

    if not filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Invalid filename: {filename!r}")

    # Base folder
    base = (DIRECT_UPLOAD_DIR / folder_rel).resolve()

    # Kind subfolder
    if kind == "edited":
        target = base / "edited" / filename
    elif kind == "dup":
        target = base / "dup" / filename
    else:  # orig
        target = base / filename

    # Security check
    root = DIRECT_UPLOAD_DIR.resolve()
    if not _is_inside(target, root):
        raise ValueError(f"Resolved path escapes DIRECT_UPLOAD_DIR: {target}")

    return target

def get_upload_dirs(user_id: int, when: Optional[datetime] = None) -> tuple[Path, Path, Path, str]:
    """
    Create/return (orig_dir, edited_dir, dup_dir, folder_rel) for this user/day:
      - orig_dir:   full path e.g. BASE/files/direct_uploads/2025_09_01_user7
      - edited_dir: subfolder 'edited'
      - dup_dir:    subfolder 'dup'
      - folder_rel: string '2025_09_01_user7' for DB storage
    """
    when = when or datetime.now(timezone.utc)
    date_str = when.strftime("%Y_%m_%d")

    # String for DB storage
    folder_rel = f"{date_str}_user{user_id}"

    # Full paths on disk
    base = ensure_root() / folder_rel
    orig_dir = base
    edited_dir = base / "edited"
    dup_dir = base / "dup"

    # Ensure dirs exist
    orig_dir.mkdir(parents=True, exist_ok=True)
    edited_dir.mkdir(parents=True, exist_ok=True)
    dup_dir.mkdir(parents=True, exist_ok=True)

    return orig_dir, edited_dir, dup_dir, folder_rel


# === Thumbnail Path Utilities ===

def get_thumbnail_path_direct(
    folder_rel: str,
    original_filename: str,
    kind: str = "orig"
) -> Path:
    """
    Get the absolute path for a direct upload thumbnail file.

    Args:
        folder_rel: Relative folder path from DB (e.g., '2025_09_01_user7')
        original_filename: Original image filename (e.g., 'abc123.jpg')
        kind: 'orig' for original image thumbnail, 'edited' for edited image thumbnail

    Returns:
        Absolute Path to thumbnail file (e.g., BASE/files/direct_uploads/2025_09_01_user7/thm_abc123.jpg)

    Raises:
        ValueError: If folder_rel or filename are invalid
    """
    if not folder_rel or "/" in folder_rel or "\\" in folder_rel:
        raise ValueError(f"Invalid folder_rel: {folder_rel!r}")

    if not original_filename or "/" in original_filename or "\\" in original_filename:
        raise ValueError(f"Invalid original_filename: {original_filename!r}")

    # Generate thumbnail filename
    thumbnail_filename = get_thumbnail_filename(original_filename)

    # Base folder
    base = (DIRECT_UPLOAD_DIR / folder_rel).resolve()

    # Determine subfolder based on kind
    if kind == "edited":
        target = base / "edited" / thumbnail_filename
    else:  # orig or thumbnail for original image
        target = base / thumbnail_filename

    # Security check - ensure it's inside DIRECT_UPLOAD_DIR
    if not _is_inside(target, DIRECT_UPLOAD_DIR.resolve()):
        raise ValueError(f"Thumbnail path escapes DIRECT_UPLOAD_DIR: {target}")

    return target


def get_thumbnail_path_encounter(encounter_file_path: Path) -> Path:
    """
    Get the absolute path for an encounter file (ZIP upload) thumbnail.

    Args:
        encounter_file_path: Full path to the encounter file

    Returns:
        Absolute Path to thumbnail file in same directory as original

    Raises:
        ValueError: If path is invalid or outside IMAGE_DIR
    """
    encounter_file_path = encounter_file_path.resolve()

    # Security check - ensure it's inside IMAGE_DIR
    if not _is_inside(encounter_file_path, IMAGE_DIR.resolve()):
        raise ValueError(f"Encounter file path escapes IMAGE_DIR: {encounter_file_path}")

    # Generate thumbnail filename
    thumbnail_filename = get_thumbnail_filename(encounter_file_path.name)

    # Thumbnail in same directory as original
    thumbnail_path = encounter_file_path.parent / thumbnail_filename

    return thumbnail_path


def thumbnail_exists_direct(
    folder_rel: str,
    original_filename: str,
    kind: str = "orig"
) -> bool:
    """
    Check if a direct upload thumbnail exists.

    Args:
        folder_rel: Relative folder path from DB
        original_filename: Original image filename
        kind: 'orig' for original, 'edited' for edited

    Returns:
        True if thumbnail file exists, False otherwise
    """
    try:
        thumbnail_path = get_thumbnail_path_direct(folder_rel, original_filename, kind)
        return thumbnail_path.exists() and thumbnail_path.is_file()
    except ValueError:
        return False


def thumbnail_exists_encounter(encounter_file_path: Path) -> bool:
    """
    Check if an encounter file thumbnail exists.

    Args:
        encounter_file_path: Full path to the encounter file

    Returns:
        True if thumbnail file exists, False otherwise
    """
    try:
        thumbnail_path = get_thumbnail_path_encounter(encounter_file_path)
        return thumbnail_path.exists() and thumbnail_path.is_file()
    except (ValueError, OSError):
        return False


def get_direct_thumbnail_serving_path(
    folder_rel: str,
    original_filename: str,
    kind: str = "orig"
) -> tuple[Path, str]:
    """
    Get directory and filename for serving a direct upload thumbnail.

    Returns a tuple (directory, filename) suitable for send_from_directory.

    Args:
        folder_rel: Relative folder path from DB
        original_filename: Original image filename
        kind: 'orig' for original, 'edited' for edited

    Returns:
        Tuple of (directory_path, thumbnail_filename)

    Raises:
        ValueError: If paths are invalid
    """
    thumbnail_path = get_thumbnail_path_direct(folder_rel, original_filename, kind)

    # For serving, we need parent directory and filename
    serving_dir = thumbnail_path.parent
    serving_filename = thumbnail_path.name

    return serving_dir, serving_filename


def get_encounter_thumbnail_serving_path(encounter_file_path: Path) -> tuple[Path, str]:
    """
    Get directory and filename for serving an encounter file thumbnail.

    Returns a tuple (directory, filename) suitable for send_from_directory.

    Args:
        encounter_file_path: Full path to the encounter file

    Returns:
        Tuple of (directory_path, thumbnail_filename)

    Raises:
        ValueError: If paths are invalid
    """
    thumbnail_path = get_thumbnail_path_encounter(encounter_file_path)

    # For serving, we need parent directory and filename
    serving_dir = thumbnail_path.parent
    serving_filename = thumbnail_path.name

    return serving_dir, serving_filename


def cleanup_orphaned_thumbnails() -> dict:
    """
    Find and optionally remove orphaned thumbnail files.

    An orphaned thumbnail is a thumbnail file whose original image no longer exists.

    Returns:
        Dictionary with cleanup statistics:
        {
            'orphaned_count': int,
            'orphaned_files': list[str],
            'cleaned_count': int,
            'errors': list[str]
        }
    """
    import os
    from utils.image_processing import THUMBNAIL_PREFIX

    stats = {
        'orphaned_count': 0,
        'orphaned_files': [],
        'cleaned_count': 0,
        'errors': []
    }

    # Check direct uploads directory
    try:
        for root, dirs, files in os.walk(DIRECT_UPLOAD_DIR):
            for file in files:
                if file.startswith(THUMBNAIL_PREFIX):
                    thumbnail_path = Path(root) / file

                    # Derive original filename
                    original_filename = file[len(THUMBNAIL_PREFIX):]
                    original_path = thumbnail_path.parent / original_filename

                    # Check if original exists (in same directory or edited subdirectory)
                    original_exists = original_path.exists()
                    if not original_exists:
                        # Check edited directory
                        edited_path = thumbnail_path.parent / "edited" / original_filename
                        original_exists = edited_path.exists()

                    if not original_exists:
                        stats['orphaned_count'] += 1
                        stats['orphaned_files'].append(str(thumbnail_path))

                        # Try to remove orphaned thumbnail
                        try:
                            thumbnail_path.unlink()
                            stats['cleaned_count'] += 1
                        except OSError as e:
                            stats['errors'].append(f"Failed to remove {thumbnail_path}: {e}")

    except Exception as e:
        stats['errors'].append(f"Error scanning direct uploads: {e}")

    # Check encounter images directory
    try:
        for root, dirs, files in os.walk(IMAGE_DIR):
            for file in files:
                if file.startswith(THUMBNAIL_PREFIX):
                    thumbnail_path = Path(root) / file

                    # Derive original filename
                    original_filename = file[len(THUMBNAIL_PREFIX):]
                    original_path = thumbnail_path.parent / original_filename

                    if not original_path.exists():
                        stats['orphaned_count'] += 1
                        stats['orphaned_files'].append(str(thumbnail_path))

                        # Try to remove orphaned thumbnail
                        try:
                            thumbnail_path.unlink()
                            stats['cleaned_count'] += 1
                        except OSError as e:
                            stats['errors'].append(f"Failed to remove {thumbnail_path}: {e}")

    except Exception as e:
        stats['errors'].append(f"Error scanning encounter images: {e}")

    return stats


def validate_thumbnail_filename(filename: str) -> bool:
    """
    Validate that a filename follows the thumbnail naming convention.

    Args:
        filename: Filename to validate

    Returns:
        True if valid thumbnail filename, False otherwise
    """
    if not filename or not isinstance(filename, str):
        return False

    from utils.image_processing import THUMBNAIL_PREFIX

    # Should start with thumbnail prefix
    if not filename.startswith(THUMBNAIL_PREFIX):
        return False

    # Extract the original filename part
    original_part = filename[len(THUMBNAIL_PREFIX):]

    # Check that original part has a valid extension
    if '.' not in original_part:
        return False

    # Basic filename validation (no path separators)
    if '/' in original_part or '\\' in original_part:
        return False

    return True


