"""Device enrolment gate, session policy, and rate-limit keying."""
from datetime import timedelta
from itertools import count

from auth.utils import utcnow
from mobile_devices.models import MobileDevice, MobileDeviceEnrolmentCode
from mobile_devices.service import (
    hash_enrolment_code,
    issue_enrolment_code,
    max_active_sessions_for,
    refresh_lifetime_for,
)
from models import Disease, Hospital, LabUnit, MobileAuthSession, Role
from services.mobile import auth_sessions
from tests.helpers.factories import UserFactory, approve_mobile_device

JWT_SECRET = "test-mobile-jwt-secret-32-chars-long"
_SEQUENCE = count(1)


def _seed_user(db_session, *, roles=("fileUploader",)):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Device Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()
    lab_unit = LabUnit(name=f"Device Lab {suffix}", hospital_id=hospital.id)
    db_session.add(lab_unit)
    db_session.flush()

    disease = db_session.query(Disease).filter_by(name="DR").first()
    if disease is None:
        disease = Disease(name="DR")
        db_session.add(disease)
        db_session.flush()

    user = UserFactory.create_grader_with_slots(
        db_session,
        username=f"device_user_{suffix}",
        hospital_id=hospital.id,
        lab_unit_id=lab_unit.id,
        disease_slots=[{"disease_id": disease.id, "can_grade_resident": True}],
        password="Test@2026",
    )
    user.hospital_id = hospital.id
    for role_name in roles:
        role = db_session.query(Role).filter_by(name=role_name).first()
        if role is None:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()
        if role not in user.roles:
            user.roles.append(role)
    db_session.flush()
    return user


def _login(client, user, device_id, **extra):
    body = {
        "username": user.username,
        "password": "Test@2026",
        "device_id": device_id,
        "device_name": "Test Device",
    }
    body.update(extra)
    return client.post("/api/mobile/v1/auth/login", json=body)


def test_login_from_unenrolled_device_returns_no_tokens(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session)

    response = _login(client, user, "unenrolled-device")

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["error"] == "device_not_enrolled"
    # The body must carry no credential material at all, not merely a non-200.
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_valid_enrolment_code_admits_the_device_in_one_request(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    admin = _seed_user(db_session, roles=("admin",))
    user = _seed_user(db_session)
    issued = issue_enrolment_code(db_session, user_id=user.id, issued_by_user_id=admin.id)
    db_session.flush()

    response = _login(client, user, "first-device", enrolment_code=issued.code, platform="android")

    assert response.status_code == 200
    assert response.get_json()["access_token"]
    device = (
        db_session.query(MobileDevice)
        .filter_by(user_id=user.id, device_id="first-device")
        .one()
    )
    assert device.status == "approved"
    assert device.platform == "android"


def test_enrolment_code_is_single_use(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    admin = _seed_user(db_session, roles=("admin",))
    user = _seed_user(db_session)
    issued = issue_enrolment_code(db_session, user_id=user.id, issued_by_user_id=admin.id)
    db_session.flush()

    assert _login(client, user, "device-a", enrolment_code=issued.code).status_code == 200

    replayed = _login(client, user, "device-b", enrolment_code=issued.code)
    assert replayed.status_code == 400
    assert replayed.get_json()["error"] == "enrolment_code_invalid"


def test_expired_enrolment_code_is_refused(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    admin = _seed_user(db_session, roles=("admin",))
    user = _seed_user(db_session)
    issued = issue_enrolment_code(db_session, user_id=user.id, issued_by_user_id=admin.id)
    row = (
        db_session.query(MobileDeviceEnrolmentCode)
        .filter_by(code_hash=hash_enrolment_code(issued.code))
        .one()
    )
    row.expires_at = utcnow() - timedelta(minutes=1)
    db_session.flush()

    response = _login(client, user, "late-device", enrolment_code=issued.code)

    assert response.status_code == 400
    assert response.get_json()["error"] == "enrolment_code_invalid"


def test_enrolment_code_cannot_enrol_a_different_user(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    admin = _seed_user(db_session, roles=("admin",))
    owner = _seed_user(db_session)
    other = _seed_user(db_session)
    issued = issue_enrolment_code(db_session, user_id=owner.id, issued_by_user_id=admin.id)
    db_session.flush()

    response = _login(client, other, "stolen-code-device", enrolment_code=issued.code)

    assert response.status_code == 400
    assert response.get_json()["error"] == "enrolment_code_invalid"


def test_blocking_a_device_ends_its_live_session_on_the_next_request(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session)
    device = approve_mobile_device(db_session, user.id, "blockable-device")

    token = _login(client, user, "blockable-device").get_json()["access_token"]
    ok = client.get("/api/mobile/v1/context/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200

    device.status = "blocked"
    db_session.flush()

    # Same still-unexpired token: revocation must not wait for token expiry.
    blocked = client.get("/api/mobile/v1/context/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 403


def test_field_user_is_capped_at_one_session_and_told_why(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session, roles=("field_optometrist",))
    approve_mobile_device(db_session, user.id, "field-device-1")
    approve_mobile_device(db_session, user.id, "field-device-2")

    first_token = _login(client, user, "field-device-1").get_json()["access_token"]
    assert _login(client, user, "field-device-2").status_code == 200

    displaced = client.get(
        "/api/mobile/v1/context/me", headers={"Authorization": f"Bearer {first_token}"}
    )
    assert displaced.status_code == 401
    # A distinguishable reason, so the app can explain rather than look broken.
    assert displaced.get_json()["message"] != "Mobile session is invalid"

    active = [
        row.device_id
        for row in db_session.query(MobileAuthSession).filter_by(user_id=user.id, is_revoked=False)
    ]
    assert active == ["field-device-2"]


def test_non_field_user_keeps_two_concurrent_sessions(db_session):
    field_user = _seed_user(db_session, roles=("field_ophthalmologist",))
    clinic_user = _seed_user(db_session, roles=("fileUploader",))

    assert max_active_sessions_for(field_user) == 1
    assert max_active_sessions_for(clinic_user) == 2


def test_refresh_lifetime_depends_on_device_kind_and_role(db_session):
    field_user = _seed_user(db_session, roles=("field_optometrist",))
    clinic_user = _seed_user(db_session, roles=("fileUploader",))

    shared = MobileDevice(user_id=field_user.id, device_id="shared-1", device_kind="shared")
    personal = MobileDevice(user_id=field_user.id, device_id="personal-1", device_kind="personal")
    legacy = MobileDevice(user_id=clinic_user.id, device_id="legacy-1", device_kind="personal")

    assert refresh_lifetime_for(shared, user=field_user) == timedelta(hours=24)
    assert refresh_lifetime_for(personal, user=field_user) == timedelta(days=7)
    assert refresh_lifetime_for(legacy, user=clinic_user) == timedelta(days=30)


def test_refresh_is_refused_once_the_device_is_blocked(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session)
    device = approve_mobile_device(db_session, user.id, "refresh-device")
    refresh_token = _login(client, user, "refresh-device").get_json()["refresh_token"]

    device.status = "blocked"
    db_session.flush()

    response = client.post(
        "/api/mobile/v1/auth/refresh",
        json={"refresh_token": refresh_token, "device_id": "refresh-device"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "device_blocked"


def test_response_reports_the_real_refresh_window_not_the_default(client, db_session, monkeypatch):
    """A shared device that reported 30 days would refresh long after expiry."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session, roles=("field_optometrist",))
    approve_mobile_device(db_session, user.id, "shared-tablet", device_kind="shared")

    payload = _login(client, user, "shared-tablet").get_json()

    one_day = int(timedelta(hours=24).total_seconds())
    assert abs(payload["refresh_expires_in"] - one_day) < 120


def test_device_refusal_does_not_burn_the_account_lockout_budget(client, db_session, monkeypatch):
    """Correct credentials on a pending device must not lock the account."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session)

    for _ in range(6):
        refused = _login(client, user, "not-yet-approved")
        assert refused.status_code == 403

    approve_mobile_device(db_session, user.id, "not-yet-approved")
    assert _login(client, user, "not-yet-approved").status_code == 200


def test_field_login_is_refused_when_the_revocation_store_is_unreachable(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session, roles=("field_optometrist",))
    approve_mobile_device(db_session, user.id, "field-redis-device")
    monkeypatch.setattr(auth_sessions, "_get_redis_client", lambda: None)

    response = _login(client, user, "field-redis-device")

    assert response.status_code == 503
    assert response.get_json()["error"] == "revocation_store_unavailable"


def test_non_field_login_still_works_without_the_revocation_store(client, db_session, monkeypatch):
    """Existing uploaders must not be taken offline by a Redis outage."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = _seed_user(db_session, roles=("fileUploader",))
    approve_mobile_device(db_session, user.id, "uploader-redis-device")
    monkeypatch.setattr(auth_sessions, "_get_redis_client", lambda: None)

    assert _login(client, user, "uploader-redis-device").status_code == 200


def test_login_rate_limit_keys_on_username_not_only_ip():
    """A per-IP-only bucket lets IP rotation defeat credential-stuffing limits."""
    from utils.rate_limiter import get_login_rate_limit_key
    from app import create_app

    app = create_app()
    with app.test_request_context(
        "/api/mobile/v1/auth/login", json={"username": "Victim", "password": "x"}
    ):
        first = get_login_rate_limit_key()
    with app.test_request_context(
        "/api/mobile/v1/auth/login",
        json={"username": "victim", "password": "x"},
        environ_overrides={"REMOTE_ADDR": "10.9.9.9"},
    ):
        second = get_login_rate_limit_key()
    with app.test_request_context(
        "/api/mobile/v1/auth/login", json={"username": "someone_else", "password": "x"}
    ):
        third = get_login_rate_limit_key()

    # Same username from a different IP shares a bucket; a different username does not.
    assert first.startswith("login:victim|")
    assert second.startswith("login:victim|")
    assert third != first


def test_mobile_rate_limit_key_separates_token_users_behind_one_ip():
    """Two field users on one clinic NAT must not share a rate-limit bucket."""
    from utils.rate_limiter import get_rate_limit_key
    from app import create_app

    app = create_app()
    with app.test_request_context("/api/mobile/v1/field/x") as ctx:
        ctx.request.mobile_auth = {"user_id": 11}
        first = get_rate_limit_key()
    with app.test_request_context("/api/mobile/v1/field/x") as ctx:
        ctx.request.mobile_auth = {"user_id": 22}
        second = get_rate_limit_key()

    assert first == "user:11"
    assert second == "user:22"
