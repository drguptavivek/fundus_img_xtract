"""
Additional utility functions for the fundus image manager.
This module contains miscellaneous helper functions that don't fit in other utility modules.
"""

import os
import hashlib
from pathlib import Path
from typing import Union, Optional, Any
from datetime import datetime
from flask import flash, current_app
from werkzeug.exceptions import NotFound
from models import Session, DIRECT_UPLOAD_DIR


def calculate_file_hash(filepath: Union[str, Path]) -> str:
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024.0 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other issues.
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove potentially dangerous characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    
    return filename

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


def get_file_extension(filename: str) -> str:
    """
    Get file extension in lowercase.
    """
    return Path(filename).suffix.lower()


def is_allowed_file_extension(filename: str, allowed_extensions: set) -> bool:
    """
    Check if file extension is in allowed extensions set.
    """
    return get_file_extension(filename) in allowed_extensions


def get_current_timestamp() -> str:
    return datetime.now().isoformat()


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_valid_uuid(uuid_string: str) -> bool:
    """
    Check if string is a valid UUID format.
    """
    import re
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(uuid_string))


def get_directory_size(path: Union[str, Path]) -> int:
    """
    Calculate total size of directory in bytes.
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    pass
    except (OSError, FileNotFoundError):
        pass
    return total_size


