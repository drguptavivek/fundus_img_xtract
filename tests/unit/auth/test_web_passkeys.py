"""Web session passkeys: username + CAPTCHA -> passkey sign-in, and account
management behind the confirm-password step."""
from __future__ import annotations

import time

from tests.conftest import create_authenticated_client

CAPTCHA = "ABC123"


def _prime_captcha(client):
    with client.session_transaction() as sess:
        sess["captcha_text"] = CAPTCHA
        sess["captcha_expiry"] = "2099-01-01T00:00:00+00:00"


def _csrf(client, path="/login"):
    page = client.get(path, follow_redirects=True)
    body = page.get_data(as_text=True)
    marker = 'name="csrf-token" content="'
    start = body.index(marker) + len(marker)
    return body[start:body.index('"', start)]


def test_passkey_options_require_captcha(client, monkeypatch):
    """The CAPTCHA verdict gates the ceremony before any user lookup. The test
    harness bypasses CAPTCHA globally, so the validator is pinned here."""
    from utils.captcha import captcha_manager

    monkeypatch.setattr(captcha_manager, "validate_captcha", lambda value: (False, "Invalid CAPTCHA. Please try again."))
    headers = {"X-CSRFToken": _csrf(client)}

    response = client.post("/login/passkey/options", json={"username": "someone", "captcha": "WRONG"}, headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error"] == "captcha_invalid"


def test_passkey_options_do_not_reveal_unknown_users(client, db_session, ophthalmologist_user):
    headers = {"X-CSRFToken": _csrf(client)}

    _prime_captcha(client)
    unknown = client.post("/login/passkey/options", json={"username": "nobody-here", "captcha": CAPTCHA}, headers=headers)
    _prime_captcha(client)
    known_without = client.post(
        "/login/passkey/options", json={"username": ophthalmologist_user.username, "captcha": CAPTCHA}, headers=headers
    )

    assert unknown.status_code == known_without.status_code == 404
    assert unknown.get_json() == known_without.get_json()


def test_passkey_verify_without_pending_ceremony_is_rejected(client):
    headers = {"X-CSRFToken": _csrf(client)}

    response = client.post("/login/passkey/verify", json={"credential": {"id": "x"}}, headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error"] == "passkey_session_missing"


def test_login_page_offers_passkey_sign_in(client):
    body = client.get("/login").get_data(as_text=True)

    assert "webauthn.js" in body
    assert "data-passkey-login" in body
    assert "/login/passkey/options" in body


def test_account_passkeys_page_needs_confirm_password(app, db_session, ophthalmologist_user):
    client = create_authenticated_client(app, ophthalmologist_user, db_session)

    response = client.get("/account/passkeys")

    assert response.status_code == 302
    assert "/confirm-password" in response.headers["Location"]

    with client.session_transaction() as sess:
        sess["last_sudo_time"] = int(time.time())
    page = client.get("/account/passkeys")
    assert page.status_code == 200
    assert "Add a passkey" in page.get_data(as_text=True)


def test_account_register_options_need_recent_sudo_then_return_webauthn_json(app, db_session, ophthalmologist_user):
    client = create_authenticated_client(app, ophthalmologist_user, db_session)
    headers = {"X-CSRFToken": _csrf(client, "/account/profile")}

    stale = client.post("/account/passkeys/register/options", json={}, headers=headers)
    assert stale.status_code == 401
    assert stale.get_json()["error"] == "reauth_required"

    with client.session_transaction() as sess:
        sess["last_sudo_time"] = int(time.time())
    fresh = client.post("/account/passkeys/register/options", json={}, headers=headers)
    assert fresh.status_code == 200, fresh.get_json()
    options = fresh.get_json()["options"]
    assert "publicKey" not in options
    assert isinstance(options["challenge"], str)
    assert options["authenticatorSelection"]["userVerification"] == "required"
