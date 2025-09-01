# direct_uploads/paths.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional
from models import BASE_DIR, DIRECT_UPLOAD_DIR

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
    Resolve absolute path from:
      - folder_rel: POSIX path relative to BASE_DIR (e.g. 'files/direct_uploads/2025_09_01_user7')
      - filename:   basename only (e.g. 'foo.jpg')
      - kind:       'orig' | 'edited'
    Ensures the final path is under DIRECT_UPLOAD_DIR.
    """
    folder_rel = (folder_rel or "").replace("\\", "/")
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Invalid basename: {filename!r}")

    base = (BASE_DIR / folder_rel).resolve()
    root = DIRECT_UPLOAD_DIR.resolve()
    if not _is_inside(base, root):
        raise ValueError(f"Folder outside DIRECT_UPLOAD_DIR: {base}")

    target = base / ("edited" if kind == "edited" else "") / filename
    return target.resolve()

def get_upload_dirs(user_id: int, when: Optional[datetime] = None) -> tuple[Path, Path, Path]:
    """
    Create/return (orig_dir, edited_dir, dup_dir) for this user/day:
      DIRECT_UPLOAD_DIR/YYYY_MM_DD_user<id>/{edited,dup}
    """
    when = when or datetime.now()
    date_str = when.strftime("%Y_%m_%d")
    base = ensure_root() / f"{date_str}_user{user_id}"
    orig_dir, edited_dir, dup_dir = base, base / "edited", base / "dup"
    orig_dir.mkdir(parents=True, exist_ok=True)
    edited_dir.mkdir(parents=True, exist_ok=True)
    dup_dir.mkdir(parents=True, exist_ok=True)
    return orig_dir, edited_dir, dup_dir

def uniquify(dest_dir: Path, filename: str) -> Path:
    p = dest_dir / filename
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 1
    while True:
        cand = dest_dir / f"{stem}__{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1
