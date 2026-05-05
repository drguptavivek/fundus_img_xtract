from itertools import count

import jwt

from auth.mobile_tokens import hash_refresh_token
from models import Disease, Hospital, LabUnit, MobileAuthSession
from services.mobile import auth_sessions
from tests.helpers.factories import UserFactory


JWT_SECRET = "test-mobile-jwt-secret-32-chars-long"
_SEQUENCE = count(1)


def _seed_mobile_user(db_session):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Mobile Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab_unit = LabUnit(name=f"Mobile Lab {suffix}", hospital_id=hospital.id)
    db_session.add(lab_unit)
    db_session.flush()

    disease = db_session.query(Disease).filter_by(name="DR").first()
    if disease is None:
        disease = Disease(name="DR")
        db_session.add(disease)
        db_session.flush()

    user = UserFactory.create_grader_with_slots(
        db_session,
        username=f"mobile_user_{suffix}",
        hospital_id=hospital.id,
        lab_unit_id=lab_unit.id,
        disease_slots=[{"disease_id": disease.id, "can_grade_resident": True}],
        password="Test@2026",
    )
    user.hospital_id = hospital.id
    db_session.flush()
    return user, hospital, lab_unit


def test_mobile_login_returns_token_shapes(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, hospital, lab_unit = _seed_mobile_user(db_session)

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-123",
            "device_name": "Pixel 9",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["token_type"] == "Bearer"
    assert payload["expires_in"] == 900
    assert payload["refresh_expires_in"] == 2592000
    assert payload["_links"]["sessions"]["href"] == "/api/mobile/v1/sessions"
    assert payload["_links"]["upload_profiles"]["href"] == "/api/mobile/v1/upload-options"
    assert payload["context"]["hospital"] == {"id": hospital.id, "name": hospital.name}
    assert payload["context"]["lab_units"] == [
        {
            "id": lab_unit.id,
            "name": lab_unit.name,
            "hospital_id": hospital.id,
            "hospital_name": hospital.name,
        }
    ]

    access_claims = jwt.decode(payload["access_token"], JWT_SECRET, algorithms=["HS256"])
    assert access_claims["sub"] == str(user.id)
    assert access_claims["typ"] == "access"
    assert access_claims["hospital_id"] == hospital.id
    assert access_claims["allowed_lab_unit_ids"] == [lab_unit.id]
    assert isinstance(payload["refresh_token"], str)
    assert len(payload["refresh_token"]) >= 32

    stored_session = db_session.query(MobileAuthSession).filter_by(user_id=user.id, device_id="device-123").one()
    assert stored_session.device_name == "Pixel 9"
    assert stored_session.refresh_token_hash == hash_refresh_token(payload["refresh_token"])


def test_mobile_login_is_exempt_from_browser_csrf(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    client.application.config["WTF_CSRF_ENABLED"] = True
    user, _, _ = _seed_mobile_user(db_session)

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-no-csrf",
            "device_name": "Mobile App",
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    assert response.get_json()["token_type"] == "Bearer"


def test_mobile_login_returns_json_when_jwt_secret_missing(client, db_session, monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    user, _, _ = _seed_mobile_user(db_session)

    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-missing-secret",
            "device_name": "Mobile App",
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 500
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "error": "server_configuration_error",
        "message": "Server configuration error",
    }


def test_mobile_context_returns_user_hospital_and_token_shape(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, hospital, lab_unit = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-ctx",
            "device_name": "iPhone",
        },
    )
    access_token = login_response.get_json()["access_token"]

    response = client.get(
        "/api/mobile/v1/context/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["user"]["id"] == user.id
    assert payload["hospital"] == {"id": hospital.id, "name": hospital.name}
    assert payload["lab_units"][0]["id"] == lab_unit.id
    assert payload["token_shape"]["access_token"]["format"] == "JWT"
    assert "mobile_session_id" in payload["token_shape"]["access_token"]["claims"]
    assert payload["token_shape"]["refresh_token"]["format"] == "opaque"


def test_mobile_refresh_rotates_refresh_token(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-refresh",
            "device_name": "Tablet",
        },
    )
    login_payload = login_response.get_json()

    refresh_response = client.post(
        "/api/mobile/v1/auth/refresh",
        json={
            "refresh_token": login_payload["refresh_token"],
            "device_id": "device-refresh",
        },
    )

    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.get_json()
    assert refresh_payload["refresh_token"] != login_payload["refresh_token"]

    rejected_old_token = client.post(
        "/api/mobile/v1/auth/refresh",
        json={
            "refresh_token": login_payload["refresh_token"],
            "device_id": "device-refresh",
        },
    )
    assert rejected_old_token.status_code == 401


def test_mobile_logout_revokes_access(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-logout",
            "device_name": "Android",
        },
    )
    login_payload = login_response.get_json()

    logout_response = client.post(
        "/api/mobile/v1/auth/logout",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert logout_response.status_code == 204

    revoked_context = client.get(
        "/api/mobile/v1/context/me",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert revoked_context.status_code == 401


def test_mobile_logout_records_access_jti_in_revoked_store(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    revoked_jtis = set()
    monkeypatch.setattr(auth_sessions, "revoke_access_jti", lambda jti, expires_at: revoked_jtis.add(jti))
    user, _, _ = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-logout-jti",
            "device_name": "Android",
        },
    )
    login_payload = login_response.get_json()
    claims = jwt.decode(login_payload["access_token"], JWT_SECRET, algorithms=["HS256"])

    logout_response = client.post(
        "/api/mobile/v1/auth/logout",
        json={"refresh_token": login_payload["refresh_token"]},
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )

    assert logout_response.status_code == 204
    assert claims["jti"] in revoked_jtis


def test_mobile_token_auth_rejects_redis_revoked_jti(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-revoked-jti",
            "device_name": "Android",
        },
    )
    access_token = login_response.get_json()["access_token"]
    claims = jwt.decode(access_token, JWT_SECRET, algorithms=["HS256"])
    monkeypatch.setattr(auth_sessions, "is_access_jti_revoked", lambda jti: jti == claims["jti"])

    response = client.get(
        "/api/mobile/v1/context/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 401
    assert response.get_json()["message"] == "Token has been revoked"


def test_mobile_sessions_endpoint_lists_current_device(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-list",
            "device_name": "Current Device",
        },
    )
    access_token = login_response.get_json()["access_token"]

    response = client.get(
        "/api/mobile/v1/sessions",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["sessions"]) == 1
    session = payload["sessions"][0]
    assert session["device_id"] == "device-list"
    assert session["is_current"] is True
    assert session["profile"]["user_id"] == user.id
    assert session["profile"]["username"] == user.username
    assert session["_links"]["self"]["href"] == f"/api/mobile/v1/sessions/{session['session_id']}"
    assert session["_links"]["revoke"] == {
        "href": f"/api/mobile/v1/sessions/{session['session_id']}/revoke",
        "method": "POST",
    }
    assert payload["_links"]["self"]["href"] == "/api/mobile/v1/sessions"
    assert payload["_links"]["upload_profiles"]["href"] == "/api/mobile/v1/upload-options"
    assert payload["_links"]["logout"] == {"href": "/api/mobile/v1/auth/logout", "method": "POST"}

    self_response = client.get(
        session["_links"]["self"]["href"],
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert self_response.status_code == 200
    assert self_response.get_json()["session_id"] == session["session_id"]


def test_legacy_mobile_auth_sessions_route_is_removed(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)
    login_response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": "device-hard-cutover",
            "device_name": "Current Device",
        },
    )
    access_token = login_response.get_json()["access_token"]

    response = client.get(
        "/api/mobile/v1/auth/sessions",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404


def test_mobile_login_revokes_oldest_session_when_more_than_two_active(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user, _, _ = _seed_mobile_user(db_session)

    for index in range(3):
        response = client.post(
            "/api/mobile/v1/auth/login",
            json={
                "username": user.username,
                "password": "Test@2026",
                "device_id": f"device-concurrent-{index}",
                "device_name": f"Device {index}",
            },
        )
        assert response.status_code == 200

    sessions = (
        db_session.query(MobileAuthSession)
        .filter_by(user_id=user.id)
        .order_by(MobileAuthSession.created_at.asc())
        .all()
    )

    assert len(sessions) == 3
    assert sessions[0].device_id == "device-concurrent-0"
    assert sessions[0].is_revoked is True
    assert sessions[0].revoked_at is not None
    assert [session.device_id for session in sessions if not session.is_revoked] == [
        "device-concurrent-1",
        "device-concurrent-2",
    ]
