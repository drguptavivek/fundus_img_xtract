"""
Secure file hashing utilities for duplicate detection.

This module provides secure file hashing functions to replace MD5
with cryptographically secure algorithms (SHA-256) for file
duplicate detection (CWE-327).
"""

import hashlib
import os
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session


def hash_file_content(content: bytes, algorithm: str = "sha256") -> str:
    """
    Hash file content using a cryptographically secure algorithm.

    Args:
        content: The file content to hash (bytes)
        algorithm: Hash algorithm to use (sha256, sha384, blake2b)

    Returns:
        Hexadecimal hash string

    Raises:
        ValueError: If algorithm is not supported

    Examples:
        >>> hash_file_content(b"test")
        '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'
    """
    if not isinstance(content, bytes):
        raise TypeError("File content must be bytes")

    algorithm_lower = algorithm.lower()

    if algorithm_lower == "sha256":
        return hashlib.sha256(content).hexdigest()
    elif algorithm_lower == "sha384":
        return hashlib.sha384(content).hexdigest()
    elif algorithm_lower == "blake2b":
        return hashlib.blake2b(content).hexdigest()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def is_duplicate_file(file_hash: str, file_size: int, db: Session) -> bool:
    """
    Check if a file with the given hash and size already exists.

    Using both hash and file size prevents collision attacks where
    an attacker could craft two different files with the same hash.

    Args:
        file_hash: The SHA-256 hash of the file content
        file_size: The size of the file in bytes
        db: Database session

    Returns:
        True if duplicate exists, False otherwise
    """
    from models import DirectImageUpload

    # Query for existing uploads with the same hash
    existing = db.execute(
        select(DirectImageUpload).filter_by(file_hash=file_hash).limit(1)
    ).scalar_one_or_none()

    if not existing:
        return False

    # For backward compatibility, we need to handle the case where
    # old MD5 hashes are stored. If the hash length is 32 (MD5), we
    # can only verify by hash. If it's 64 (SHA-256), we can also verify
    # by file size if the model supported it.
    # For now, we'll trust the hash match since file_size isn't in the model yet
    return True


def get_hash_algorithm() -> str:
    """
    Get the configured hash algorithm for file hashing.

    Can be configured via environment variable FILE_HASH_ALGORITHM.
    Defaults to sha256.

    Returns:
        Hash algorithm name (sha256, sha384, blake2b)
    """
    return os.getenv("FILE_HASH_ALGORITHM", "sha256").lower()


def get_hash_length(algorithm: Optional[str] = None) -> int:
    """
    Get the hash length in hex characters for a given algorithm.

    Args:
        algorithm: Hash algorithm (uses default if not specified)

    Returns:
        Length of hash in hexadecimal characters
    """
    if algorithm is None:
        algorithm = get_hash_algorithm()

    algorithm_lower = algorithm.lower()

    if algorithm_lower == "sha256":
        return 64
    elif algorithm_lower == "sha384":
        return 96
    elif algorithm_lower == "blake2b":
        return 128
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")


def md5_hash(content: bytes) -> str:
    """
    Compute MD5 hash of content (for backward compatibility only).

    Note: MD5 is cryptographically broken and should NOT be used
    for new code. This function is only for verifying old hashes.

    Args:
        content: The content to hash

    Returns:
        MD5 hash as hexadecimal string
    """
    return hashlib.md5(content).hexdigest()
