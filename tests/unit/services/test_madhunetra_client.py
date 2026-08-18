from __future__ import annotations

import requests

from models import AIModelIntegration
from services.madhunetra_client import MadhuNetrAIClient, MadhuNetrAIError


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}
        self.content = b"{}" if payload is not None else b""
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


class Session:
    def __init__(self, posts=None, puts=None):
        self.posts = list(posts or [])
        self.puts = list(puts or [])
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        value = self.posts.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        value = self.puts.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_presign_uses_token_scheme_and_submit_timeout():
    session = Session(
        posts=[
            Response(payload={"request_id": "abc", "uploads": []}),
            Response(payload={"request_id": "abc", "status": "completed"}),
        ]
    )
    client = MadhuNetrAIClient(base_url="https://wai.example/", token="secret", session=session)

    client.presign(request_id="abc", images=[])
    client.submit(request_id="abc", patient={"patient_id": "p", "age": 2}, images=[])

    assert session.calls[0][2]["headers"]["Authorization"] == "Token secret"
    assert session.calls[1][2]["timeout"] == 180


def test_upload_has_only_content_type_and_retries_after_three_and_five_seconds():
    sleeps = []
    session = Session(puts=[Response(503), requests.ConnectionError("signed URL secret"), Response(200)])
    client = MadhuNetrAIClient(
        base_url="https://wai.example", token="secret", session=session, sleep=sleeps.append
    )

    attempts = client.upload(upload_url="https://storage.example/signed", content_type="image/jpeg", image_bytes=b"jpeg")

    assert attempts == 3
    assert sleeps == [3, 5]
    assert all(call[2]["headers"] == {"Content-Type": "image/jpeg"} for call in session.calls)
    assert all("Authorization" not in call[2]["headers"] for call in session.calls)


def test_authentication_error_uses_stable_code():
    session = Session(posts=[Response(401, {"detail": "Invalid token."})])
    client = MadhuNetrAIClient(base_url="https://wai.example", token="secret", session=session)

    try:
        client.presign(request_id="abc", images=[])
    except MadhuNetrAIError as exc:
        assert exc.code == "authentication_failed"
        assert "secret" not in str(exc)
    else:
        raise AssertionError("expected authentication error")


def test_submit_timeout_does_not_include_request_or_secret_in_error():
    session = Session(posts=[requests.Timeout("https://wai.example/?token=secret")] * 4)
    client = MadhuNetrAIClient(base_url="https://wai.example", token="secret", session=session, sleep=lambda _: None)

    try:
        client.submit(request_id="patient-sensitive", patient={}, images=[])
    except MadhuNetrAIError as exc:
        assert exc.code == "network_error"
        assert "secret" not in str(exc)
        assert "patient-sensitive" not in str(exc)
    else:
        raise AssertionError("expected timeout")


def test_submit_reuses_payload_with_documented_backoff():
    sleeps = []
    session = Session(
        posts=[
            Response(502, {"error": "model_unavailable", "detail": "busy"}),
            Response(502, {"error": "model_unavailable", "detail": "busy"}),
            Response(payload={"request_id": "stable", "status": "completed"}),
        ]
    )
    client = MadhuNetrAIClient(base_url="https://wai.example", token="secret", session=session, sleep=sleeps.append)

    result = client.submit(request_id="stable", patient={"patient_id": "p", "age": 2}, images=[])

    assert result["status"] == "completed"
    assert sleeps == [2, 10]
    assert [call[2]["json"]["request_id"] for call in session.calls] == ["stable"] * 3


def test_integration_encrypts_access_token_at_rest(app):
    integration = AIModelIntegration(
        ai_model_id=1,
        provider="wai_dr_dme",
        client_id="vision-centre",
        bearer_token="",
    )
    with app.app_context():
        integration.set_access_token("plain-secret")
        assert integration.access_token_encrypted != "plain-secret"
        assert integration.get_access_token() == "plain-secret"
