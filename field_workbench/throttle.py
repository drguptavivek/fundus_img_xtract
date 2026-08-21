"""Minimum spacing between one user's fetch requests.

The rate limiter expresses rates ("2 per minute"), not spacing, so it would
happily allow two requests in the same second. Field taps translate into many
upstream calls, so a hard gap is enforced here with a Redis key.
"""
from __future__ import annotations

import logging

import redis

from utils.log_sanitize import sanitize_log_value
from utils.redis_connection import build_redis_url

from .exceptions import FieldThrottled

logger = logging.getLogger("field_workbench.throttle")

FETCH_MIN_INTERVAL_SECONDS = 30
_KEY_PREFIX = "field:fetch:user:"

_client: redis.Redis | None = None


def _redis() -> redis.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        _client = redis.Redis.from_url(build_redis_url(), decode_responses=True)
        _client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Field fetch throttle unavailable: %s", sanitize_log_value(exc))
        _client = None
    return _client


def enforce_fetch_spacing(user_id: int, *, interval_seconds: int = FETCH_MIN_INTERVAL_SECONDS) -> None:
    """Raise :class:`FieldThrottled` if this user asked too recently.

    A Redis outage does not block the request: the per-user rate limit and the
    per-project coalescing guard both still apply, so failing open here costs
    spacing but not protection.
    """
    client = _redis()
    if client is None:
        return
    key = f"{_KEY_PREFIX}{user_id}"
    try:
        acquired = client.set(key, "1", nx=True, ex=interval_seconds)
    except redis.RedisError as exc:
        logger.warning("Field fetch throttle check failed: %s", sanitize_log_value(exc))
        return
    if acquired:
        return
    try:
        retry_after = int(client.ttl(key) or interval_seconds)
    except redis.RedisError:
        retry_after = interval_seconds
    raise FieldThrottled(
        f"Please wait {max(retry_after, 1)}s before requesting another fetch.",
        retry_after=max(retry_after, 1),
    )


def reset_fetch_spacing(user_id: int) -> None:
    """Clear the gap for one user. Used by tests."""
    client = _redis()
    if client is None:
        return
    try:
        client.delete(f"{_KEY_PREFIX}{user_id}")
    except redis.RedisError:
        pass
