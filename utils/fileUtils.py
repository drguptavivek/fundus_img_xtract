from datetime import datetime
import mimetypes
import os
from pathlib import Path
from typing import Optional
from flask import Response, abort, send_file
from werkzeug.utils import secure_filename
from models import ALLOWED_IMAGE_EXT, BASE_DIR, DIRECT_UPLOAD_DIR, IMAGE_DIR, PDF_DIR, Session, EncounterFile, PatientEncounters, ZipFile

 
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
    when = when or datetime.now()
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


