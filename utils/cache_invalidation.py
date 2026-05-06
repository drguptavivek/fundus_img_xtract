"""Shared cache invalidation helpers."""

from __future__ import annotations

from flask import current_app

from app_cache import cache
from utils.log_sanitize import sanitize_log_value

DISCREPANCY_REVIEW_CACHE_KEY_PREFIX = "discrepancy-review:"


def _decode_cache_key(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def delete_cache_keys_by_route_prefix(route_key_prefix: str) -> int:
    """Delete Flask-Caching keys whose un-prefixed route key starts with route_key_prefix."""
    backend = getattr(cache, "cache", None)
    if backend is None:
        return 0

    key_prefix = getattr(backend, "key_prefix", None)
    if key_prefix is None:
        key_prefix = current_app.config.get("CACHE_KEY_PREFIX", "")
    if isinstance(key_prefix, bytes):
        key_prefix = key_prefix.decode("utf-8", errors="ignore")

    cache_key_prefix = f"{key_prefix}{route_key_prefix}"
    redis_client = (
        getattr(backend, "_write_client", None)
        or getattr(backend, "_client", None)
        or getattr(backend, "client", None)
    )
    if redis_client is not None and hasattr(redis_client, "scan_iter"):
        deleted = 0
        batch = []
        for key in redis_client.scan_iter(match=f"{cache_key_prefix}*", count=1000):
            batch.append(key)
            if len(batch) >= 1000:
                deleted += redis_client.delete(*batch)
                batch = []
        if batch:
            deleted += redis_client.delete(*batch)
        return int(deleted)

    local_cache = getattr(backend, "_cache", None)
    if isinstance(local_cache, dict):
        matching_keys = [
            key
            for key in list(local_cache.keys())
            if _decode_cache_key(key).startswith(cache_key_prefix)
        ]
        for key in matching_keys:
            del local_cache[key]
        return len(matching_keys)

    current_app.logger.warning(
        "Unable to invalidate cache keys for prefix %s: unsupported cache backend %s",
        sanitize_log_value(route_key_prefix),
        sanitize_log_value(type(backend).__name__),
    )
    return 0


def invalidate_discrepancy_review_cache() -> int:
    """Invalidate cached discrepancy-review pages after grading data changes."""
    try:
        deleted = delete_cache_keys_by_route_prefix(DISCREPANCY_REVIEW_CACHE_KEY_PREFIX)
        current_app.logger.info(
            "Invalidated %s discrepancy-review cache entries",
            sanitize_log_value(deleted),
        )
        return deleted
    except Exception:
        current_app.logger.exception("Failed to invalidate discrepancy-review cache")
        return 0
