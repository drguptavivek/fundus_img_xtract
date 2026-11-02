"""Regressions for DAST-022 through DAST-029."""
from unittest.mock import Mock

import pytest
from flask import Flask

from app_init.security_headers import register_csp
from tests.helpers.mobile_auth import mobile_login
from tests.unit.api.test_mobile_auth import _seed_mobile_user
from utils.captcha import CaptchaManager, captcha_manager

_validate_captcha = CaptchaManager.validate_captcha


@pytest.mark.parametrize("platform", [None, "web", "android", "ios", "unknown"])
def test_platform_cannot_skip_captcha(client, platform, monkeypatch):
    monkeypatch.setattr(captcha_manager, "validate_captcha", _validate_captcha.__get__(captcha_manager))
    payload = dict(username="grader", password="wrong", device_id="device", device_name="test")
    if platform is not None:
        payload["platform"] = platform
    response = client.post("/api/mobile/v1/auth/login", json=payload)
    assert response.status_code == 400
    assert response.json["error"] == "captcha_invalid"


def test_failed_logins_commit_counters_and_four_hour_locks(client, db_session, monkeypatch):
    import db_transaction_manager
    from auth.routes import MAX_FAILS_PER_USERNAME
    from auth.utils import utcnow
    from models import LoginAttempt, IpLock

    user, _, _ = _seed_mobile_user(db_session)
    session_wrapper = db_transaction_manager.DbSession()
    commit = Mock(wraps=session_wrapper.commit)
    rollback = Mock(wraps=session_wrapper.rollback)
    monkeypatch.setattr(session_wrapper, "commit", commit)
    monkeypatch.setattr(session_wrapper, "rollback", rollback)
    for _ in range(MAX_FAILS_PER_USERNAME):
        response = mobile_login(client, json=dict(
            username=user.username, password="wrong", device_id="device", device_name="test"
        ))
        assert response.status_code == 401
    assert commit.call_count >= MAX_FAILS_PER_USERNAME
    rollback.assert_not_called()
    assert db_session.query(LoginAttempt).filter_by(username_input=user.username, success=False).count() == MAX_FAILS_PER_USERNAME
    db_session.refresh(user)
    assert (user.is_locked_until - utcnow()).total_seconds() > 14390
    assert db_session.query(IpLock).count() >= 1
    response = mobile_login(client, json=dict(
        username=user.username, password="Test@2026", device_id="device", device_name="test"
    ))
    assert response.status_code == 403
    assert response.json["error"] in {"ip_locked", "user_locked"}


def test_logout_get_cannot_end_session(client):
    with client.session_transaction() as session:
        session["logout_sentinel"] = "preserved"
    response = client.get("/logout")
    assert response.status_code in {302, 405}
    with client.session_transaction() as session:
        assert session["logout_sentinel"] == "preserved"


def test_debug_endpoint_removed(app):
    assert "/test-rate-limit" not in {rule.rule for rule in app.url_map.iter_rules()}


@pytest.mark.parametrize("path,content_type", [
    ("/analytics", "text/html"), ("/api/error", "application/json"),
    ("/static/test.js", "application/javascript"), ("/image", "image/png"),
])
def test_security_headers_cover_early_returns(path, content_type):
    app = Flask(__name__)
    register_csp(app)
    app.add_url_rule(path, view_func=lambda: ("test", 401, {"Content-Type": content_type}))
    response = app.test_client().get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_cors_defaults_closed(monkeypatch):
    from app import _parse_cors_origins
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    assert _parse_cors_origins() == []
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://trusted.example")
    assert _parse_cors_origins() == ["https://trusted.example"]
    from flask_cors import CORS
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": _parse_cors_origins()}}, supports_credentials=True, always_send=False)
    app.add_url_rule("/api/test", view_func=lambda: ("error", 401))
    for origin in [None, "http://127.0.0.1:5001", "https://evil.example", "null"]:
        headers = {"Origin": origin} if origin else {}
        response = app.test_client().get("/api/test", headers=headers)
        assert "Access-Control-Allow-Origin" not in response.headers
    response = app.test_client().get("/api/test", headers={"Origin": "https://trusted.example"})
    assert response.headers["Access-Control-Allow-Origin"] == "https://trusted.example"


@pytest.mark.parametrize("rotate_accounts,rotate_ips,attempts", [(True, False, 21), (False, True, 11)])
def test_login_limits_stop_spraying_and_ip_rotation(monkeypatch, rotate_accounts, rotate_ips, attempts):
    from contextlib import contextmanager
    from flask_limiter import Limiter
    from auth.utils import get_client_ip
    from api.mobile import auth

    app = Flask(__name__)
    app.secret_key = "test-only"
    Limiter(key_func=get_client_ip, app=app, storage_uri="memory://")
    app.add_url_rule("/login", view_func=auth.login, methods=["POST"])

    @contextmanager
    def transaction():
        yield object()

    def deny(*args):
        raise auth.MobileAuthError("Invalid credentials", code="invalid_credentials", status_code=401)

    monkeypatch.setattr(auth, "authentication_transaction", transaction)
    monkeypatch.setattr(auth, "login_mobile_user", deny)
    monkeypatch.setattr(auth, "require_web_captcha", lambda *args: None)
    client = app.test_client()
    for index in range(attempts):
        response = client.post("/login", json=dict(
            username=f"user{index}" if rotate_accounts else "victim",
            password="wrong", device_id="device", device_name="test"
        ), environ_overrides={"REMOTE_ADDR": f"10.0.0.{index + 1}" if rotate_ips else "10.0.0.1"})
        assert response.status_code == (429 if index == attempts - 1 else 401), (index, response.get_data(as_text=True))


@pytest.mark.parametrize("missing", ["exp", "typ", "jti", "iat", "sub", "mobile_session_id"])
def test_incomplete_signed_access_tokens_are_rejected(client, db_session, monkeypatch, missing):
    import jwt
    from tests.unit.api.test_mobile_auth import JWT_SECRET
    from tests.helpers.factories import approve_mobile_device
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    approve_mobile_device(db_session, user.id, "claims-device")
    tokens = mobile_login(client, json=dict(username=user.username, password="Test@2026", device_id="claims-device", device_name="test")).json
    claims = jwt.decode(tokens["access_token"], JWT_SECRET, algorithms=["HS256"])
    claims.pop(missing)
    token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")
    assert client.get("/api/mobile/v1/context/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_subject_must_match_mobile_session(client, db_session, monkeypatch):
    import jwt
    from tests.unit.api.test_mobile_auth import JWT_SECRET
    from tests.helpers.factories import approve_mobile_device
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    approve_mobile_device(db_session, user.id, "subject-device")
    tokens = mobile_login(client, json=dict(username=user.username, password="Test@2026", device_id="subject-device", device_name="test")).json
    claims = jwt.decode(tokens["access_token"], JWT_SECRET, algorithms=["HS256"])
    claims["sub"] = str(user.id + 100000)
    token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")
    assert client.get("/api/mobile/v1/context/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_rotated_refresh_token_cannot_be_reused(client, db_session, monkeypatch):
    from tests.unit.api.test_mobile_auth import JWT_SECRET
    from tests.helpers.factories import approve_mobile_device
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    approve_mobile_device(db_session, user.id, "rotation-device")
    tokens = mobile_login(client, json=dict(username=user.username, password="Test@2026", device_id="rotation-device", device_name="test")).json
    payload = dict(refresh_token=tokens["refresh_token"], device_id="rotation-device")
    assert client.post("/api/mobile/v1/auth/refresh", json=payload).status_code == 200
    response = client.post("/api/mobile/v1/auth/refresh", json=payload)
    assert response.status_code == 401
    assert response.json["error"] == "invalid_refresh_token"


def test_reauth_failures_commit_and_revoke_session(client, db_session, monkeypatch):
    import db_transaction_manager
    from models import MobileAuthSession
    from tests.unit.api.test_mobile_auth import JWT_SECRET
    from tests.helpers.factories import approve_mobile_device
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    approve_mobile_device(db_session, user.id, "reauth-lock-device")
    tokens = mobile_login(client, json=dict(username=user.username, password="Test@2026", device_id="reauth-lock-device", device_name="test", platform="android")).json
    wrapper = db_transaction_manager.DbSession()
    commit = Mock(wraps=wrapper.commit)
    rollback = Mock(wraps=wrapper.rollback)
    monkeypatch.setattr(wrapper, "commit", commit)
    monkeypatch.setattr(wrapper, "rollback", rollback)
    for _ in range(5):
        response = client.post("/api/mobile/v1/auth/reauth", json={"password": "wrong"}, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert response.status_code == 401
    assert commit.call_count >= 5
    rollback.assert_not_called()
    row = db_session.query(MobileAuthSession).filter_by(user_id=user.id, device_id="reauth-lock-device").one()
    assert row.is_revoked and row.revoked_reason == "reauth_failed"
    assert client.get("/api/mobile/v1/context/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401


def test_blocked_device_refresh_commits_revocation(client, db_session, monkeypatch):
    import db_transaction_manager
    from models import MobileAuthSession
    from tests.unit.api.test_mobile_auth import JWT_SECRET
    from tests.helpers.factories import approve_mobile_device
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    device = approve_mobile_device(db_session, user.id, "revocation-device")
    tokens = mobile_login(client, json=dict(username=user.username, password="Test@2026", device_id="revocation-device", device_name="test")).json
    device.status = "blocked"
    db_session.flush()
    wrapper = db_transaction_manager.DbSession()
    commit = Mock(wraps=wrapper.commit)
    rollback = Mock(wraps=wrapper.rollback)
    monkeypatch.setattr(wrapper, "commit", commit)
    monkeypatch.setattr(wrapper, "rollback", rollback)
    payload = dict(refresh_token=tokens["refresh_token"], device_id="revocation-device")
    assert client.post("/api/mobile/v1/auth/refresh", json=payload).status_code == 403
    assert commit.call_count >= 1
    rollback.assert_not_called()
    row = db_session.query(MobileAuthSession).filter_by(user_id=user.id, device_id="revocation-device").one()
    assert row.is_revoked
    device.status = "approved"
    db_session.flush()
    assert client.post("/api/mobile/v1/auth/refresh", json=payload).status_code == 401
