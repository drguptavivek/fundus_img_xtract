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
    # ProxyFix has already selected the configured trusted proxy hop. Parsing
    # forwarded headers again lets a supplied prefix evade lockout/IP bans.
    return _valid_ip(request.remote_addr or "") or "0.0.0.0"
