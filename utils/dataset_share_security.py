"""Redis-backed lockouts for dataset share attempts."""

from __future__ import annotations

import logging
from typing import Optional

import redis

from utils.redis_connection import build_redis_url

_LOGGER = logging.getLogger("security")

LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 30 * 60
FAILURE_WINDOW_SECONDS = 30 * 60

_redis_client: Optional[redis.Redis] = None


def _get_redis_client() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis.from_url(build_redis_url(), decode_responses=True)
    except Exception as exc:
        _LOGGER.error("Dataset share Redis init failed: %s", exc)
        _redis_client = None
    return _redis_client


def _key_prefix(ip: str, token_hash: str) -> str:
    token_hint = (token_hash or "")[:16]
    return f"dataset_share:{ip}:{token_hint}"


def is_locked_out(ip: str, token_hash: str) -> bool:
    client = _get_redis_client()
    if not client:
        return False
    key = f"{_key_prefix(ip, token_hash)}:lockout"
    try:
        return bool(client.exists(key))
    except Exception as exc:
        _LOGGER.error("Dataset share lockout check failed: %s", exc)
        return False


def register_failure(ip: str, token_hash: str) -> bool:
    client = _get_redis_client()
    if not client:
        return False
    fail_key = f"{_key_prefix(ip, token_hash)}:failures"
    lock_key = f"{_key_prefix(ip, token_hash)}:lockout"
    try:
        count = client.incr(fail_key)
        if count == 1:
            client.expire(fail_key, FAILURE_WINDOW_SECONDS)
        if count >= LOCKOUT_THRESHOLD:
            client.setex(lock_key, LOCKOUT_SECONDS, "1")
            return True
        return False
    except Exception as exc:
        _LOGGER.error("Dataset share failure tracking failed: %s", exc)
        return False


def clear_failures(ip: str, token_hash: str) -> None:
    client = _get_redis_client()
    if not client:
        return
    fail_key = f"{_key_prefix(ip, token_hash)}:failures"
    try:
        client.delete(fail_key)
    except Exception as exc:
        _LOGGER.error("Dataset share failure reset failed: %s", exc)
