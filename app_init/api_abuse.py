"""Shared source-IP bans for repeated API authentication and probing failures."""
from __future__ import annotations

import hashlib
import logging
import time

import redis
from flask import g, jsonify, request

from utils.log_sanitize import sanitize_log_value
from utils.redis_connection import build_redis_url

logger = logging.getLogger("security.api_abuse")
FAILURE_LIMIT = 20
WINDOW_SECONDS = 600
BAN_SECONDS = 14400
BAN_INDEX_KEY = "fim:security:api_abuse:v1:active_bans"

_RECORD = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
if count >= tonumber(ARGV[2]) then
  local banned = redis.call('SET', KEYS[2], '1', 'EX', ARGV[3], 'NX')
  if banned then
    redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', ARGV[4])
    redis.call('ZADD', KEYS[3], tonumber(ARGV[4]) + tonumber(ARGV[3]), ARGV[5])
    return 1
  end
end
return 0
"""


def api_abuse_keys(ip_address: str) -> tuple[str, str]:
    digest = hashlib.sha256(ip_address.encode()).hexdigest()
    prefix = f"fim:security:api_abuse:v1:{digest}"
    return prefix + ":failures", prefix + ":ban"


def register_api_abuse_guard(app) -> None:
    client = None

    def backend():
        nonlocal client
        supplied = app.extensions.get("api_abuse_backend")
        if supplied is not None:
            return supplied
        if client is None:
            client = redis.Redis.from_url(build_redis_url(), socket_connect_timeout=1, socket_timeout=1)
            app.extensions["api_abuse_backend"] = client
        return client

    def enabled():
        return app.config.get("API_ABUSE_GUARD_ENABLED", not app.testing)

    def keys():
        # ProxyFix already selects the trusted proxy hop. Never parse a second,
        # attacker-controlled forwarded-header value to choose the ban bucket.
        return api_abuse_keys(request.remote_addr or "unknown")

    def unavailable():
        response = jsonify({"error": "security_backend_unavailable", "message": "Authentication is temporarily unavailable. Retry later."})
        response.status_code = 503
        response.headers["Retry-After"] = "60"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def check_ban():
        if not enabled() or not request.path.startswith("/api/"):
            return None
        g.api_abuse_started = time.monotonic()
        try:
            remaining = backend().ttl(keys()[1])
        except redis.RedisError as exc:
            logger.error("API abuse backend unavailable ip=%s error=%s", sanitize_log_value(request.remote_addr), sanitize_log_value(type(exc).__name__))
            return unavailable()
        if remaining > 0:
            g.api_abuse_blocked = True
            logger.warning("API source banned ip=%s method=%s endpoint=%s", sanitize_log_value(request.remote_addr), request.method, sanitize_log_value(request.endpoint or "unmatched"))
            response = jsonify({"error": "ip_temporarily_banned", "message": "Repeated rejected requests. Retry after the temporary block expires."})
            response.status_code = 429
            response.headers["Retry-After"] = str(remaining)
            response.headers["Cache-Control"] = "no-store"
            return response
        g.api_abuse_checked = True
        return None

    @app.after_request
    def record_failure(response):
        if not getattr(g, "api_abuse_checked", False):
            return response
        # 403 is a scope denial, 404 includes enumeration of hidden resources.
        # 429 is deliberately excluded: normal sync backpressure is not abuse.
        if response.status_code not in {401, 403, 404}:
            return response
        try:
            failure_key, ban_key = keys()
            newly_banned = backend().eval(_RECORD, 3, failure_key, ban_key, BAN_INDEX_KEY,
                                         WINDOW_SECONDS, FAILURE_LIMIT, BAN_SECONDS,
                                         int(time.time()), request.remote_addr or "unknown")
        except redis.RedisError as exc:
            logger.error("API abuse recording failed ip=%s error=%s", sanitize_log_value(request.remote_addr), sanitize_log_value(type(exc).__name__))
            # Never release a protected response when enforcement is unavailable.
            return unavailable()
        logger.warning("API access rejected ip=%s method=%s endpoint=%s status=%s banned=%s", sanitize_log_value(request.remote_addr), request.method, sanitize_log_value(request.endpoint or "unmatched"), response.status_code, bool(newly_banned))
        if newly_banned:
            logger.warning("API IP ban imposed ip=%s seconds=%s failures=%s window_seconds=%s", sanitize_log_value(request.remote_addr), BAN_SECONDS, FAILURE_LIMIT, WINDOW_SECONDS)
            try:
                from db_transaction_manager import transaction_scope
                from security_incidents.service import record_ip_ban
                with transaction_scope() as db:
                    record_ip_ban(db, ip_address=request.remote_addr or "unknown",
                                  endpoint=request.endpoint or "unmatched", method=request.method)
            except Exception as exc:
                logger.error("IP ban audit persistence failed error=%s", sanitize_log_value(type(exc).__name__))
        return response
