"""Startup environment validation."""
from __future__ import annotations

import logging
import os
from typing import List, Tuple

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix


def _mask_url_password(url: str) -> str:
    """Mask credentials in URLs before logging."""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        netloc = parts.hostname or ""
        if parts.username:
            masked_user = parts.username
            if parts.password:
                masked_user += ":***"
            netloc = f"{masked_user}@{netloc}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return url


def run_startup_env_checks(app: Flask, startup_env_logger: logging.Logger) -> None:
    """Validate critical deployment assumptions and log any issues for operators."""
    findings: List[Tuple[str, str]] = []

    secure_cookie = bool(app.config.get("SESSION_COOKIE_SECURE", False))
    same_site = str(app.config.get("SESSION_COOKIE_SAMESITE", "")).lower()
    force_https_env = str(os.getenv("FORCE_HTTPS", "false")).lower() in ("1", "true", "yes")
    if same_site == "none" and not secure_cookie:
        findings.append(
            (
                "error",
                "SESSION_COOKIE_SAMESITE=None requires SESSION_COOKIE_SECURE=true or browsers will drop the cookie.",
            )
        )
    if secure_cookie and not force_https_env:
        findings.append(
            (
                "warning",
                "SESSION_COOKIE_SECURE is enabled but FORCE_HTTPS is not; proxy traffic over plain HTTP will strip the cookie.",
            )
        )

    proxy_fix_applied = isinstance(app.wsgi_app, ProxyFix)
    if not proxy_fix_applied:
        findings.append(
            (
                "error",
                "ProxyFix wrapper is missing; X-Forwarded-* headers will be ignored and scheme detection will be incorrect.",
            )
        )
    else:
        x_proto = getattr(app.wsgi_app, "x_proto", 0)
        if force_https_env and x_proto < 1:
            findings.append(
                (
                    "warning",
                    "FORCE_HTTPS is true but TRUST_PROXY_HOPS (x_proto) is < 1; forwarded proto may not be honored.",
                )
            )

    redis_url = (
        app.config.get("RATELIMIT_REDIS_URL") or app.config.get("REDIS_URL") or os.getenv("REDIS_URL")
    )
    if redis_url:
        try:
            import redis  # type: ignore[import-not-found]

            client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
            if not client.ping():  # pragma: no cover - defensive
                findings.append(("error", f"Redis ping returned falsy for {_mask_url_password(redis_url)}"))
        except Exception as exc:  # pragma: no cover - best effort
            findings.append(("error", f"Redis unreachable at {_mask_url_password(redis_url)}: {exc}"))
    else:
        findings.append(("warning", "No Redis URL configured; rate limiting may fall back to in-memory storage."))

    for level, message in findings:
        log_fn = startup_env_logger.error if level == "error" else startup_env_logger.warning
        log_fn(message)
    if not findings:
        startup_env_logger.info("Startup environment checks passed.")

    @app.before_request
    def _log_forwarded_headers_once() -> None:
        """Log the first observed forwarded headers to diagnose proxy issues."""
        if app.config.get("_forwarded_headers_logged"):
            return
        headers_of_interest = {
            "X-Forwarded-For": request.headers.get("X-Forwarded-For"),
            "X-Forwarded-Proto": request.headers.get("X-Forwarded-Proto"),
            "X-Forwarded-Host": request.headers.get("X-Forwarded-Host"),
            "Forwarded": request.headers.get("Forwarded"),
        }
        startup_env_logger.info("First request forwarded header snapshot: %s", headers_of_interest)
        app.config["_forwarded_headers_logged"] = True

