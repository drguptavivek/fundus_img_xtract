"""Shared helpers for media cache versioning."""

from __future__ import annotations

import time
from typing import Optional

from app_cache import cache

_MEDIA_VERSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _media_version_key(uuid: str) -> str:
    return f"media:version:{uuid}"


def get_media_cache_version(uuid: Optional[str]) -> str:
    """Return the current cache version for a media UUID."""
    if not uuid:
        return "0"
    version = cache.get(_media_version_key(uuid))
    return version if isinstance(version, str) else "0"


def bump_media_cache_version(uuid: Optional[str]) -> str:
    """Bump cache version for a media UUID so future requests bypass stale cache."""
    if not uuid:
        return "0"
    version = str(int(time.time() * 1000))
    cache.set(_media_version_key(uuid), version, timeout=_MEDIA_VERSION_TTL_SECONDS)
    return version
