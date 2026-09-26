"""Server-wide concurrency gate for sync traffic.

Gunicorn runs a handful of sync workers shared with graders. Desktop mirrors
are bulk and non-urgent, so at most ``PROJECT_SYNC_MAX_CONCURRENT`` sync
requests may be in flight across every worker process at once; the rest get
``429`` with ``Retry-After`` and the client waits its turn. A slot is held
until the response has finished streaming, not merely until the view returns.

A lease expiry reclaims slots from crashed workers. If Redis is unreachable
the gate fails closed: sync is deferrable, grading is not.
"""
from __future__ import annotations

import logging
import time
import uuid

import redis
from flask import current_app

from utils.log_sanitize import sanitize_log_value
from utils.redis_connection import build_redis_url

from .exceptions import ProjectSyncError

logger = logging.getLogger("project_sync.throttle")

_KEY = "project_sync:inflight"
LEASE_SECONDS = 300
RETRY_AFTER_SECONDS = 5

_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[3]) then
  redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
  return 1
end
return 0
"""

_client: redis.Redis | None = None


class ProjectSyncBusy(ProjectSyncError):
    status_code = 429
    code = "sync_busy"

    def __init__(self, message: str = "Server is busy; retry later.", retry_after: int = RETRY_AFTER_SECONDS):
        super().__init__(message)
        self.retry_after = retry_after


def _redis() -> redis.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        _client = redis.Redis.from_url(build_redis_url(), decode_responses=True)
        _client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Project sync throttle unavailable: %s", sanitize_log_value(exc))
        _client = None
    return _client


def max_concurrent() -> int:
    return max(1, int(current_app.config.get("PROJECT_SYNC_MAX_CONCURRENT", 1)))


def acquire_slot() -> str:
    """Return a lease token, or raise :class:`ProjectSyncBusy`."""
    client = _redis()
    if client is None:
        raise ProjectSyncBusy("Sync is temporarily unavailable; retry later.", retry_after=60)
    token = uuid.uuid4().hex
    now = time.time()
    try:
        acquired = client.eval(_ACQUIRE, 1, _KEY, now, now + LEASE_SECONDS, max_concurrent(), token, LEASE_SECONDS * 2)
    except redis.RedisError as exc:
        logger.warning("Project sync throttle check failed: %s", sanitize_log_value(exc))
        raise ProjectSyncBusy("Sync is temporarily unavailable; retry later.", retry_after=60) from None
    if not acquired:
        raise ProjectSyncBusy()
    return token


def release_slot(token: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.zrem(_KEY, token)
    except redis.RedisError as exc:
        logger.warning("Project sync slot release failed: %s", sanitize_log_value(exc))
