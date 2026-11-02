"""Submit mobile login with a solved, session-bound test CAPTCHA."""
from datetime import timedelta

from auth.utils import utcnow


def mobile_login(client, *, json, **kwargs):
    with client.session_transaction() as session:
        session["captcha_text"] = "AC234"
        session["captcha_expiry"] = (utcnow() + timedelta(minutes=5)).isoformat()
    return client.post("/api/mobile/v1/auth/login", json={**json, "captcha": "AC234"}, **kwargs)
