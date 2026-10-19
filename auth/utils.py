# auth/utils.py — client IP + time helpers
import ipaddress

from flask import request
from datetime import datetime, timedelta, timezone

def utcnow():
    return datetime.now(timezone.utc)

def _valid_ip(value: str) -> str | None:
    """Return the normalised IP literal, or None for anything else (hostnames, payloads)."""
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def get_client_ip() -> str:
    # Align with your logging precedence: X-Forwarded-For then X-Real-IP then remote_addr.
    # Header values are client-controlled: only valid IP literals are accepted so they
    # always fit the 45-char ip_address columns and never carry injected payloads.
    # If behind a proxy, ensure proxy sets X-Forwarded-For and Flask is not trusting arbitrary headers.
    for header in ("X-Forwarded-For", "X-Real-IP"):
        for raw in request.headers.getlist(header):
            ip = _valid_ip(raw.split(",")[0])
            if ip:
                return ip
    return _valid_ip(request.remote_addr or "") or "0.0.0.0"
