# auth/utils.py — client IP + time helpers
from flask import request
from datetime import datetime, timedelta, timezone

def utcnow():
    return datetime.now(timezone.utc)

def get_client_ip() -> str:
    # Align with your logging precedence: X-Forwarded-For then remote_addr
    # If behind a proxy, ensure proxy sets X-Forwarded-For and Flask is not trusting arbitrary headers.
    xff = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return xff or (request.remote_addr or "0.0.0.0")
