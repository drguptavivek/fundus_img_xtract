"""
Filename sanitization utilities for storage-safe filenames.

Provides ASCII-safe, collision-resistant filenames for local storage and S3 keys
while preserving file extensions.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


_NONSAFE_RE = re.compile(r'[^A-Za-z0-9._-]+')
_UNDERSCORE_RE = re.compile(r'_+')


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def _ascii_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = _NONSAFE_RE.sub("_", ascii_value)
    ascii_value = ascii_value.replace("..", "_")
    ascii_value = _UNDERSCORE_RE.sub("_", ascii_value).strip("._-")
    return ascii_value


def sanitize_path_component(component: str, max_length: int = 200) -> str:
    """
    Sanitize a single path component to ASCII-safe form.

    Adds a short hash suffix if sanitization changes the component
    to avoid collisions.
    """
    if not component or not component.strip():
        raise ValueError("Path component cannot be empty")
    if "\x00" in component:
        raise ValueError("Null bytes detected in path component")

    ascii_component = _ascii_slug(component)
    if not ascii_component:
        ascii_component = "part"

    changed = ascii_component != component
    if changed:
        suffix = _short_hash(component)
        base = ascii_component
        max_base_len = max_length - 1 - len(suffix)
        if max_base_len < 1:
            base = "part"
            max_base_len = max_length - 1 - len(suffix)
        base = base[:max_base_len]
        return f"{base}_{suffix}"

    return ascii_component[:max_length]


def sanitize_storage_filename(filename: str, max_length: int = 255, allow_no_ext: bool = False) -> str:
    """
    Sanitize a filename for storage while preserving the extension.

    Non-ASCII characters are transliterated to ASCII. If sanitization changes the
    name, a short hash suffix is appended to avoid collisions.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename is empty")
    if "\x00" in filename:
        raise ValueError("Null bytes detected in filename")

    if "." in filename:
        base, ext = filename.rsplit(".", 1)
    else:
        if not allow_no_ext:
            raise ValueError("Filename must include a file extension")
        base, ext = filename, ""

    base_ascii = _ascii_slug(base) or "file"
    ext_ascii = _ascii_slug(ext)
    if ext and not ext_ascii:
        ext_ascii = "dat"

    changed = (base_ascii != base) or (ext_ascii != ext)

    suffix = _short_hash(filename) if changed else ""

    if ext_ascii:
        # Reserve space: base + "_" + hash + "." + ext
        reserve = 1 + len(suffix) + 1 + len(ext_ascii) if changed else 1 + len(ext_ascii)
        max_base_len = max_length - reserve
        if max_base_len < 1:
            max_base_len = 1
        base_ascii = base_ascii[:max_base_len]
        if changed:
            base_ascii = f"{base_ascii}_{suffix}"
        return f"{base_ascii}.{ext_ascii}"

    # No extension
    reserve = 1 + len(suffix) if changed else 0
    max_base_len = max_length - reserve
    if max_base_len < 1:
        max_base_len = 1
    base_ascii = base_ascii[:max_base_len]
    if changed:
        base_ascii = f"{base_ascii}_{suffix}"
    return base_ascii
