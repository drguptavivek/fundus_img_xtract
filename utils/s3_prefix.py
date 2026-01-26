"""
Global S3 prefix handling.

All S3 object keys are stored under a single, fixed prefix.
"""

from utils.s3_validation import validate_s3_object_key

GLOBAL_S3_PREFIX = "eyeimgmgr"


def apply_global_prefix(object_key: str) -> str:
    """
    Prepend the global S3 prefix to an object key.

    Expects object_key WITHOUT the global prefix. If the prefix is already
    present, the key is returned unchanged after validation.
    """
    if not object_key:
        raise ValueError("object_key cannot be empty")

    object_key = object_key.lstrip("/")
    prefix = f"{GLOBAL_S3_PREFIX}/"

    if object_key.startswith(prefix):
        return validate_s3_object_key(object_key)

    return validate_s3_object_key(f"{prefix}{object_key}")
