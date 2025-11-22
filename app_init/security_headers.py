"""CSP nonce generation and security headers."""
from __future__ import annotations

import secrets
from typing import Callable

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

        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{script_nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
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
            "upgrade-insecure-requests",
        ]

        csp = "; ".join(csp_directives)
        response.headers["Content-Security-Policy"] = csp
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        return response

