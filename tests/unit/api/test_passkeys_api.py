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
