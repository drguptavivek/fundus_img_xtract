"""
S3 path mapping utilities.

Maps local filesystem paths to S3 object keys that mirror /files layout.
"""

from pathlib import Path

from models import BASE_DIR
from utils.s3_validation import validate_s3_object_key


def s3_key_from_rel_path(rel_path: str) -> str:
    """
    Validate and normalize a path relative to BASE_DIR for S3 storage.
    """
    if not rel_path:
        raise ValueError("rel_path cannot be empty")
    rel_path = rel_path.lstrip("/")
    return validate_s3_object_key(rel_path)


def s3_key_from_local_path(local_path: Path | str) -> str:
    """
    Convert a local absolute path to an S3 object key relative to BASE_DIR.
    """
    base_dir = BASE_DIR.resolve()
    abs_path = Path(local_path).resolve()

    if not abs_path.is_relative_to(base_dir):
        raise ValueError(f"Local path is outside BASE_DIR: {abs_path}")

    rel_path = abs_path.relative_to(base_dir).as_posix()
    return s3_key_from_rel_path(rel_path)
