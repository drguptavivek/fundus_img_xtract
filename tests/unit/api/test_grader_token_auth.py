"""Grader PWA on mobile bearer tokens: web devices skip enrolment, a valid
access token resolves current_user on session-protected routes, and CSRF is
skipped only for bearer-authenticated requests."""
from __future__ import annotations

from tests.helpers.factories import UserFactory
from tests.unit.api.test_mobile_auth import JWT_SECRET, _seed_mobile_user


def _login_web(client, user, device_id="browser-1"):
    return client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": device_id,
            "device_name": "Chrome on macOS",
            "platform": "web",
        },
    )


def test_web_platform_login_skips_enrolment(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)

    response = _login_web(client, user)

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["access_token"] and payload["refresh_token"]
    from mobile_devices.models import MobileDevice

    device = db_session.query(MobileDevice).filter_by(user_id=user.id, device_id="browser-1").one()
    assert device.status == "approved"
    assert device.platform == "web"


def test_non_web_platform_still_requires_enrolment(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "phone-1",
            "device_name": "Pixel 9",
            "platform": "android",
        },
    )

    assert response.status_code in (403, 409), response.get_json()
    assert response.get_json()["error"] != "invalid_credentials"


def test_web_auto_approval_can_be_disabled(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    client.application.config["MOBILE_WEB_DEVICES_AUTO_APPROVE"] = False
    try:
        user, _, _ = _seed_mobile_user(db_session)
        response = _login_web(client, user, device_id="browser-off")
        assert response.status_code in (403, 409)
    finally:
        client.application.config.pop("MOBILE_WEB_DEVICES_AUTO_APPROVE", None)


def test_blocked_browser_device_stays_blocked(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    from mobile_devices.models import MobileDevice

    db_session.add(MobileDevice(user_id=user.id, device_id="browser-blocked", status="blocked", platform="web"))
    db_session.flush()

    response = _login_web(client, user, device_id="browser-blocked")

    assert response.status_code in (403, 409)


def test_bearer_token_resolves_current_user_on_grader_pages_and_api(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    token = _login_web(client, user).get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Anonymous: the guard sends /grader/ to the PWA's own login page.
    anonymous = client.get("/grader/")
    assert anonymous.status_code == 302
    assert "/grader/login" in anonymous.headers["Location"]

    # Bearer: the page renders for a grader with no web session at all.
    page = client.get("/grader/", headers=headers)
    assert page.status_code == 200, page.get_data(as_text=True)[:200]
    # A bearer request must never turn into a logged-in web session.
    with client.session_transaction() as web_session:
        assert "_user_id" not in web_session

    # A client without the header is anonymous (fresh client: the test client
    # keeps one app context across calls, unlike real requests).
    assert client.application.test_client().get("/grader/").status_code == 302

    # Bearer on a session-protected JSON API, POST without a CSRF token: the
    # request reaches the domain layer instead of failing CSRF.
    api = client.post(
        "/api/grading/workbench/acquire",
        headers=headers,
        json={"disease_id": 999999, "role_slot": "resident"},
    )
    assert api.status_code != 400 or api.get_json().get("success") is False
    assert "CSRF" not in api.get_data(as_text=True)
    assert api.is_json


def test_bearer_without_grading_role_is_forbidden(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    uploader = UserFactory.create_optometrist(db_session, username="pwa_token_optometrist")
    db_session.flush()
    response = _login_web(client, uploader, device_id="browser-opt")
    assert response.status_code == 200, response.get_json()
    token = response.get_json()["access_token"]

    page = client.get("/grader/", headers={"Authorization": f"Bearer {token}"})

    assert page.status_code == 403


def test_invalid_bearer_leaves_request_anonymous(client):
    response = client.get("/grader/", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 302
    assert "/grader/login" in response.headers["Location"]


def test_grader_login_page_is_public(client):
    response = client.get("/grader/login")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "grader-auth.js" in body
    assert "data-grader-login" in body
    assert 'name="username"' in body and 'name="password"' in body
    assert response.headers["Cache-Control"] == "no-store"


def test_heartbeat_does_not_count_as_activity(client, db_session, monkeypatch):
    """The 30-minute gate measures the user, not the workbench's automatic heartbeat."""
    from datetime import timedelta

    from auth.utils import utcnow
    from models import MobileAuthSession

    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    token = _login_web(client, user, device_id="browser-hb").get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    mobile_session = db_session.query(MobileAuthSession).filter_by(user_id=user.id, device_id="browser-hb").one()
    stale = utcnow() - timedelta(minutes=45)
    mobile_session.last_used_at = stale
    db_session.flush()
    db_session.commit()

    # A heartbeat after 45 idle minutes is refused and leaves the idle clock untouched.
    heartbeat = client.post("/api/grading/workbench/sessions/none/heartbeat", headers=headers, json={})
    assert heartbeat.status_code == 401
    assert heartbeat.get_json()["error"]["code"] == "reauth_required"
    db_session.expire_all()
    mobile_session = db_session.query(MobileAuthSession).filter_by(user_id=user.id, device_id="browser-hb").one()
    assert abs((mobile_session.last_used_at - stale).total_seconds()) < 2


def test_idle_session_requires_reauth_and_password_reauth_clears_it(client, db_session, monkeypatch):
    from datetime import timedelta

    from auth.utils import utcnow
    from models import MobileAuthSession

    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    token = _login_web(client, user, device_id="browser-idle").get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    mobile_session = db_session.query(MobileAuthSession).filter_by(user_id=user.id, device_id="browser-idle").one()
    mobile_session.last_used_at = utcnow() - timedelta(minutes=31)
    db_session.flush()
    db_session.commit()

    gated = client.get("/grader/", headers=headers)
    assert gated.status_code == 302
    assert "reauth=1" in gated.headers["Location"]

    wrong = client.post("/api/mobile/v1/auth/reauth", headers=headers, json={"password": "nope"})
    assert wrong.status_code == 401

    fresh = client.post("/api/mobile/v1/auth/reauth", headers=headers, json={"password": "Test@2026"})
    assert fresh.status_code == 200, fresh.get_json()
    new_token = fresh.get_json()["access_token"]
    assert fresh.get_json()["method"] == "password"

    page = client.get("/grader/", headers={"Authorization": f"Bearer {new_token}"})
    assert page.status_code == 200


def test_bearer_token_does_not_authenticate_outside_the_grader_surface(client, db_session, monkeypatch):
    """A stolen grader token must not reach the rest of the web app."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    token = _login_web(client, user, device_id="browser-scope").get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for path in ("/grading/", "/admin/", "/account", "/api/grading-dashboard-not-in-list"):
        response = client.application.test_client().get(path, headers=headers)
        assert response.status_code in (302, 308, 404), path
        if response.status_code in (302, 308):
            assert "/login" in response.headers["Location"], path

    # ...while the grader surface itself works.
    assert client.application.test_client().get("/grader/", headers=headers).status_code == 200
