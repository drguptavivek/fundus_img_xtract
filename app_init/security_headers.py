"""CSP nonce generation and security headers."""
from __future__ import annotations

import secrets
from typing import Callable
import os

from flask import Flask, g, request
from werkzeug.wrappers.response import Response


def register_csp(app: Flask) -> None:
    """Register CSP nonce helpers and response headers."""

    @app.context_processor
    def inject_csp_nonces() -> dict[str, Callable[[], str]]:
        def get_script_nonce() -> str:
            return getattr(g, "csp_script_nonce", "")

        def get_style_nonce() -> str:
            return getattr(g, "csp_style_nonce", "")

        return {"csp_script_nonce": get_script_nonce, "csp_style_nonce": get_style_nonce}

    @app.before_request
    def generate_csp_nonces() -> None:
        """Generate CSP nonces before request processing."""
        g.csp_script_nonce = secrets.token_urlsafe(16)
        g.csp_style_nonce = secrets.token_urlsafe(16)

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        """Add comprehensive security headers including CSP with nonces."""
        content_type = response.headers.get("Content-Type", "").lower()
        path = request.path

        if response.headers.get("Content-Security-Policy"):
            return response

        if (
            path.startswith("/static/")
            or path.startswith("/api/")
            or content_type.startswith("image/")
            or content_type.startswith("application/pdf")
        ):
            return response

        script_nonce = getattr(g, "csp_script_nonce", "")
        style_nonce = getattr(g, "csp_style_nonce", "")

        # Check if we're in development mode
        is_development = (
            app.debug or
            str(os.getenv("FLASK_ENV", "production")).lower() == "development" or
            str(os.getenv("DEBUG", "false")).lower() in ("1", "true", "yes")
        )

        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com",
            "img-src 'self' data: blob: https:",
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:",
            "connect-src 'self' https://eye.epidemiology.tech https://eyeimg.aiims.edu.in https://eyeimg.aiims.edu https://cdn.jsdelivr.net",
            "media-src 'self' data: blob:",
            "frame-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
              "frame-ancestors 'self'",
            "manifest-src 'self'",
            "worker-src 'self' blob:",
        ]

        # Only add upgrade-insecure-requests in production
        if not is_development:
            csp_directives.append("upgrade-insecure-requests")

        csp = "; ".join(csp_directives)
        response.headers["Content-Security-Policy"] = csp
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        # Add HSTS header only in production (CWE-523)
        # HSTS prevents downgrade attacks from HTTPS to HTTP
        if not is_development:
            # Get HSTS configuration from environment
            max_age = os.getenv("HSTS_MAX_AGE", "31536000")  # 1 year default
            include_subdomains = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "true").lower() in ("1", "true", "yes")
            preload = os.getenv("HSTS_PRELOAD", "false").lower() in ("1", "true", "yes")

            hsts_parts = [f"max-age={max_age}"]
            if include_subdomains:
                hsts_parts.append("includeSubDomains")
            if preload:
                hsts_parts.append("preload")

            response.headers["Strict-Transport-Security"] = "; ".join(hsts_parts)

        return response
