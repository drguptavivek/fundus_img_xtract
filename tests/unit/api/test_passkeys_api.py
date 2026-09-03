"""Passkey ceremonies: options are the inner WebAuthn JSON, registration needs a
recent password proof, and challenge state is single-use."""
from __future__ import annotations

from tests.unit.api.test_grader_token_auth import _login_web
from tests.unit.api.test_mobile_auth import JWT_SECRET, _seed_mobile_user


def test_register_options_are_webauthn_json(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    token = _login_web(client, user, device_id="browser-pk").get_json()["access_token"]

    response = client.post("/api/mobile/v1/auth/passkeys/register/options", headers={"Authorization": f"Bearer {token}"}, json={})

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["challenge_id"]
    options = payload["options"]
    assert "publicKey" not in options, "must be the inner options object"
    assert isinstance(options["challenge"], str)
    assert options["rp"]["id"] == "localhost"
    assert isinstance(options["user"]["id"], str)
    assert options["authenticatorSelection"]["userVerification"] == "required"


def test_register_verify_rejects_bad_credential_and_consumes_challenge(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    headers = {"Authorization": f"Bearer {_login_web(client, user, device_id='browser-pk2').get_json()['access_token']}"}
    challenge_id = client.post("/api/mobile/v1/auth/passkeys/register/options", headers=headers, json={}).get_json()["challenge_id"]

    bad = client.post(
        "/api/mobile/v1/auth/passkeys/register/verify",
        headers=headers,
        json={"challenge_id": challenge_id, "credential": {"id": "x", "rawId": "eA", "type": "public-key", "response": {}}},
    )
    assert bad.status_code == 400
    assert bad.get_json()["error"] == "registration_failed"

    replay = client.post(
        "/api/mobile/v1/auth/passkeys/register/verify",
        headers=headers,
        json={"challenge_id": challenge_id, "credential": {"id": "x", "rawId": "eA", "type": "public-key", "response": {}}},
    )
    assert replay.get_json()["error"] == "challenge_expired"


def test_reauth_options_require_a_registered_passkey(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    headers = {"Authorization": f"Bearer {_login_web(client, user, device_id='browser-pk3').get_json()['access_token']}"}

    response = client.post("/api/mobile/v1/auth/passkeys/reauth/options", headers=headers, json={})

    assert response.status_code == 404
    assert response.get_json()["error"] == "no_passkey"


def _seed_passkey(db_session, user, credential_id="Z3JhZGVyLXBhc3NrZXk"):
    from fido2 import cbor

    from passkeys.models import MobilePasskey

    db_session.add(
        MobilePasskey(
            user_id=user.id,
            credential_id=credential_id,
            public_key=cbor.encode({1: 2, 3: -7, -1: 1, -2: b"\x05" * 32, -3: b"\x06" * 32}),
            sign_count=0,
        )
    )
    db_session.flush()
    db_session.commit()


def test_passkey_login_options_hide_unknown_users(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)

    unknown = client.post("/api/mobile/v1/auth/passkeys/login/options", json={"username": "ghost"})
    without = client.post("/api/mobile/v1/auth/passkeys/login/options", json={"username": user.username})

    assert unknown.status_code == without.status_code == 404
    assert unknown.get_json() == without.get_json()


def test_passkey_login_options_for_a_user_with_a_passkey(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    _seed_passkey(db_session, user)

    response = client.post("/api/mobile/v1/auth/passkeys/login/options", json={"username": user.username})

    assert response.status_code == 200, response.get_json()
    options = response.get_json()["options"]
    assert options["allowCredentials"][0]["id"] == "Z3JhZGVyLXBhc3NrZXk"
    assert options["userVerification"] == "required"


def test_passkey_login_verify_rejects_a_bad_assertion(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    _seed_passkey(db_session, user, credential_id="dmVyaWZ5LXRlc3Q")
    challenge_id = client.post("/api/mobile/v1/auth/passkeys/login/options", json={"username": user.username}).get_json()["challenge_id"]

    response = client.post(
        "/api/mobile/v1/auth/passkeys/login/verify",
        json={
            "username": user.username, "challenge_id": challenge_id, "device_id": "browser-pk-login",
            "device_name": "Safari on macOS", "platform": "web",
            "credential": {"id": "x", "rawId": "eA", "type": "public-key", "response": {}},
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "invalid_credentials"
    assert "access_token" not in response.get_json()


def test_passkey_login_options_require_captcha_for_web(client, db_session, monkeypatch):
    from utils.captcha import captcha_manager

    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    _seed_passkey(db_session, user, credential_id="Y2FwdGNoYS10ZXN0")
    monkeypatch.setattr(captcha_manager, "validate_captcha", lambda value, **kwargs: (False, "Invalid CAPTCHA. Please try again."))

    response = client.post(
        "/api/mobile/v1/auth/passkeys/login/options", json={"username": user.username, "platform": "web", "captcha": "WRONG"}
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "captcha_invalid"
