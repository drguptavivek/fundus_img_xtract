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

    monkeypatch.setattr(captcha_manager, "validate_captcha", lambda value, **kwargs: (False, "Invalid CAPTCHA. Please try again."))
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


def test_web_reauth_passkey_is_shown_only_for_enrolled_users(app, db_session, ophthalmologist_user, monkeypatch):
    client = create_authenticated_client(app, ophthalmologist_user, db_session)
    monkeypatch.setattr("passkeys.service.list_passkeys", lambda *args, **kwargs: [])
    assert b'id="reauth-passkey"' not in client.get("/confirm-password").data
    monkeypatch.setattr("passkeys.service.list_passkeys", lambda *args, **kwargs: [object()])
    assert b'id="reauth-passkey"' in client.get("/confirm-password").data


def test_web_reauth_passkey_binds_challenge_to_session_and_safely_redirects(app, db_session, ophthalmologist_user, monkeypatch):
    client = create_authenticated_client(app, ophthalmologist_user, db_session)
    headers = {"X-CSRFToken": _csrf(client, "/account/profile")}
    monkeypatch.setattr("passkeys.service.begin_assertion", lambda db, user: {"challenge_id": "correct", "options": {}})
    calls = []
    monkeypatch.setattr("passkeys.service.complete_assertion", lambda db, **kwargs: calls.append(kwargs["user"].id))
    options = client.post("/api/auth/reauth/passkey/options", json={}, headers=headers)
    assert options.status_code == 200
    mismatch = client.post("/api/auth/reauth/passkey/verify", json={"challenge_id": "wrong", "credential": {}}, headers=headers)
    assert mismatch.status_code == 400
    assert not calls
    with client.session_transaction() as sess:
        assert "last_sudo_time" not in sess

    options_response = client.post("/api/auth/reauth/passkey/options", json={}, headers=headers)
    assert options_response.status_code == 200, options_response.get_data(as_text=True)
    result = client.post("/api/auth/reauth/passkey/verify", json={"challenge_id": "correct", "credential": {"id": "credential"}, "next": "https://evil.example/"}, headers=headers)
    assert result.status_code == 200
    assert result.get_json()["redirect_url"] != "https://evil.example/"
    assert calls == [ophthalmologist_user.id]
    with client.session_transaction() as sess:
        assert sess["last_sudo_time"] >= int(time.time()) - 10
    assert client.post("/api/auth/reauth/passkey/verify", json={"challenge_id": "correct", "credential": {}}, headers=headers).status_code == 400


def test_web_reauth_rejects_failed_assertion_without_refreshing_session(app, db_session, ophthalmologist_user, monkeypatch):
    from passkeys.service import PasskeyError
    client = create_authenticated_client(app, ophthalmologist_user, db_session)
    headers = {"X-CSRFToken": _csrf(client, "/account/profile")}
    monkeypatch.setattr("passkeys.service.begin_assertion", lambda db, user: {"challenge_id": "correct", "options": {}})
    def fail(*args, **kwargs):
        raise PasskeyError("Invalid assertion", code="assertion_failed", status_code=401)
    monkeypatch.setattr("passkeys.service.complete_assertion", fail)
    client.post("/api/auth/reauth/passkey/options", json={}, headers=headers)
    response = client.post("/api/auth/reauth/passkey/verify", json={"challenge_id": "correct", "credential": {}}, headers=headers)
    assert response.status_code == 401
    with client.session_transaction() as sess:
        assert "last_sudo_time" not in sess


def test_web_reauth_requires_csrf_and_session_challenge(app, db_session, ophthalmologist_user, monkeypatch):
    client = create_authenticated_client(app, ophthalmologist_user, db_session)
    other_session = create_authenticated_client(app, ophthalmologist_user, db_session)
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    monkeypatch.setattr("passkeys.service.begin_assertion", lambda db, user: {"challenge_id": "correct", "options": {}})
    assert client.post("/api/auth/reauth/passkey/options", json={}).status_code == 400
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    options_response = client.post("/api/auth/reauth/passkey/options", json={})
    assert options_response.status_code == 200, options_response.get_data(as_text=True)
    response = other_session.post("/api/auth/reauth/passkey/verify", json={"challenge_id": "correct", "credential": {}})
    assert response.status_code == 400
    with other_session.session_transaction() as sess:
        assert "last_sudo_time" not in sess


def test_web_reauth_real_challenge_rejects_invalid_credential(app, db_session, ophthalmologist_user):
    from fido2 import cbor
    from passkeys.models import MobilePasskey

    db_session.add(MobilePasskey(
        user_id=ophthalmologist_user.id,
        credential_id="dGVzdC1jcmVkZW50aWFs",
        public_key=cbor.encode({1: 2, 3: -7, -1: 1, -2: b"\x01" * 32, -3: b"\x02" * 32}),
        sign_count=0,
        aaguid="AAAAAAAAAAAAAAAAAAAAAA",
    ))
    db_session.commit()
    client = create_authenticated_client(app, ophthalmologist_user, db_session)
    headers = {"X-CSRFToken": _csrf(client, "/account/profile")}
    options = client.post("/api/auth/reauth/passkey/options", json={}, headers=headers)
    assert options.status_code == 200
    assert options.json["options"]["userVerification"] == "required"
    response = client.post("/api/auth/reauth/passkey/verify", json={"challenge_id": options.json["challenge_id"], "credential": {"id": "invalid"}}, headers=headers)
    assert response.status_code == 401
    with client.session_transaction() as sess:
        assert "last_sudo_time" not in sess


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


def test_passkey_options_for_a_user_with_a_passkey(client, db_session, ophthalmologist_user):
    """Options come back and the pending ceremony is parked in the session."""
    from fido2 import cbor

    from passkeys.models import MobilePasskey

    db_session.add(
        MobilePasskey(
            user_id=ophthalmologist_user.id,
            credential_id="dGVzdC1jcmVkZW50aWFs",
            public_key=cbor.encode({1: 2, 3: -7, -1: 1, -2: b"\x01" * 32, -3: b"\x02" * 32}),
            sign_count=0,
            aaguid="AAAAAAAAAAAAAAAAAAAAAA",
            label="Test authenticator",
        )
    )
    db_session.flush()
    db_session.commit()
    headers = {"X-CSRFToken": _csrf(client)}
    _prime_captcha(client)

    response = client.post(
        "/login/passkey/options", json={"username": ophthalmologist_user.username, "captcha": CAPTCHA}, headers=headers
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["challenge_id"]
    assert isinstance(payload["options"]["challenge"], str)
    assert payload["options"]["allowCredentials"][0]["id"] == "dGVzdC1jcmVkZW50aWFs"
    with client.session_transaction() as sess:
        pending = sess["passkey_login"]
        assert pending["user_id"] == ophthalmologist_user.id
        assert pending["challenge_id"] == payload["challenge_id"]


def _password_login(client, user, **extra):
    csrf = _csrf(client)
    _prime_captcha(client)
    return client.post(
        "/login",
        data={"username": user.username, "password": "Test@2026", "captcha": CAPTCHA, "csrf_token": csrf, **extra},
        follow_redirects=False,
    )


def test_two_step_login_markup(client):
    body = client.get("/login").get_data(as_text=True)

    assert 'data-login-step="1"' in body and 'data-login-step="2"' in body
    assert 'id="next-btn"' in body
    assert "Sign in with password" in body


def test_password_login_without_passkey_offers_enrolment(client, db_session, ophthalmologist_user):
    response = _password_login(client, ophthalmologist_user)

    assert response.status_code == 302
    assert "/account/passkeys/offer" in response.headers["Location"]
    assert "next=" in response.headers["Location"]

    offer = client.get(response.headers["Location"])
    assert offer.status_code == 200
    assert "Add a passkey for this device" in offer.get_data(as_text=True)

    # The password just entered authorises enrolment without confirm-password.
    options = client.post("/account/passkeys/register/options", json={}, headers={"X-CSRFToken": _csrf(client, "/account/profile")})
    assert options.status_code == 200, options.get_json()


def test_offer_can_be_dismissed_for_this_device(client, db_session, ophthalmologist_user):
    _password_login(client, ophthalmologist_user)
    csrf = _csrf(client, "/account/profile")

    dismissed = client.post("/account/passkeys/offer/dismiss", data={"next": "/grading/", "csrf_token": csrf})
    assert dismissed.status_code == 302
    assert dismissed.headers["Location"].endswith("/grading/")
    assert "passkey_offer_dismissed=1" in dismissed.headers.get("Set-Cookie", "")

    client.get("/logout")
    again = _password_login(client, ophthalmologist_user)
    assert "/account/passkeys/offer" not in again.headers["Location"]


def test_password_login_with_passkey_skips_offer(client, db_session, ophthalmologist_user):
    from fido2 import cbor

    from passkeys.models import MobilePasskey

    db_session.add(
        MobilePasskey(
            user_id=ophthalmologist_user.id,
            credential_id="b2ZmZXItdGVzdA",
            public_key=cbor.encode({1: 2, 3: -7, -1: 1, -2: b"\x03" * 32, -3: b"\x04" * 32}),
            sign_count=0,
        )
    )
    db_session.flush()
    db_session.commit()

    response = _password_login(client, ophthalmologist_user)

    assert response.status_code == 302
    assert "/account/passkeys/offer" not in response.headers["Location"]
