from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import timedelta
from typing import Any

import jwt
from flask import request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from models import Hospital, LabUnit, MobileAuthSession, User, UserDiseaseUnitRole
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("auth.mobile")

ACCESS_TOKEN_LIFETIME = timedelta(minutes=15)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET not configured")
    return secret


def _token_hash_secret() -> bytes:
    secret = (
        os.environ.get("MOBILE_AUTH_TOKEN_PEPPER")
        or os.environ.get("AUTH_PEPPER")
        or os.environ.get("JWT_SECRET")
        or os.environ.get("FLASK_SECRET_KEY")
    )
    if not secret:
        raise RuntimeError("No secret configured for mobile token hashing")
    return secret.encode("utf-8")


def hash_refresh_token(token: str) -> str:
    return hmac.new(_token_hash_secret(), token.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _csv_to_ints(raw_value: str | None) -> list[int]:
    if not raw_value:
        return []
    out: list[int] = []
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            logger.warning("Invalid stored mobile scope value: %s", sanitize_log_value(part))
    return sorted(set(out))


def _ints_to_csv(values: list[int]) -> str | None:
    cleaned = sorted({int(value) for value in values})
    if not cleaned:
        return None
    return ",".join(str(value) for value in cleaned)


def build_mobile_scope(db, user: User) -> dict[str, Any]:
    db_user = db.execute(
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.lab_units).selectinload(LabUnit.hospital),
            selectinload(User.hospital),
        )
        .where(User.id == user.id)
    ).scalar_one()

    permission_rows = db.execute(
        select(UserDiseaseUnitRole)
        .where(UserDiseaseUnitRole.user_id == user.id)
        .where(UserDiseaseUnitRole.active == True)  # noqa: E712
    ).scalars().all()

    permission_lab_unit_ids = {row.lab_unit_id for row in permission_rows}
    disease_ids = {row.disease_id for row in permission_rows}

    scoped_lab_units = []
    seen_lab_unit_ids = set()
    for lab_unit in db_user.lab_units:
        scoped_lab_units.append(
            {
                "id": lab_unit.id,
                "name": lab_unit.name,
                "hospital_id": lab_unit.hospital_id,
                "hospital_name": lab_unit.hospital.name if lab_unit.hospital else None,
            }
        )
        seen_lab_unit_ids.add(lab_unit.id)

    if permission_lab_unit_ids:
        extra_lab_units = db.execute(
            select(LabUnit)
            .options(selectinload(LabUnit.hospital))
            .where(LabUnit.id.in_(permission_lab_unit_ids))
        ).scalars().all()
        for lab_unit in extra_lab_units:
            if lab_unit.id in seen_lab_unit_ids:
                continue
            scoped_lab_units.append(
                {
                    "id": lab_unit.id,
                    "name": lab_unit.name,
                    "hospital_id": lab_unit.hospital_id,
                    "hospital_name": lab_unit.hospital.name if lab_unit.hospital else None,
                }
            )
            seen_lab_unit_ids.add(lab_unit.id)

    hospital_payload = None
    if db_user.hospital_id:
        hospital = db_user.hospital or db.get(Hospital, db_user.hospital_id)
        if hospital:
            hospital_payload = {"id": hospital.id, "name": hospital.name}

    return {
        "hospital": hospital_payload,
        "lab_units": sorted(scoped_lab_units, key=lambda item: (item["hospital_name"] or "", item["name"])),
        "allowed_lab_unit_ids": sorted(seen_lab_unit_ids),
        "allowed_disease_ids": sorted(disease_ids),
        "roles": sorted(role.name for role in (db_user.roles or [])),
    }


def _encode_access_token(user: User, mobile_session: MobileAuthSession, scope: dict[str, Any]) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "typ": "access",
        "jti": secrets.token_hex(16),
        "mobile_session_id": mobile_session.id,
        "hospital_id": user.hospital_id,
        "allowed_lab_unit_ids": scope["allowed_lab_unit_ids"],
        "allowed_disease_ids": scope["allowed_disease_ids"],
        "roles": scope["roles"],
        "iat": now,
        "exp": now + ACCESS_TOKEN_LIFETIME,
        # Seconds since epoch of the last password / passkey proof on this
        # session; the grading gate reads it alongside session activity.
        "auth_time": int((mobile_session.last_authenticated_at or now).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def create_mobile_session(
    db,
    user: User,
    device_id: str,
    device_name: str,
    refresh_lifetime: timedelta | None = None,
) -> tuple[MobileAuthSession, str, str, dict[str, Any]]:
    scope = build_mobile_scope(db, user)
    now = utcnow()
    lifetime = refresh_lifetime or REFRESH_TOKEN_LIFETIME
    refresh_token = generate_refresh_token()
    refresh_hash = hash_refresh_token(refresh_token)

    mobile_session = db.execute(
        select(MobileAuthSession)
        .where(MobileAuthSession.user_id == user.id)
        .where(MobileAuthSession.device_id == device_id)
    ).scalar_one_or_none()

    if mobile_session is None:
        mobile_session = MobileAuthSession(
            user_id=user.id,
            device_id=device_id,
            device_name=device_name,
            refresh_token_hash=refresh_hash,
            refresh_token_expires_at=now + lifetime,
            last_used_at=now,
            last_authenticated_at=now,
            last_refreshed_at=now,
            last_used_ip=request.remote_addr,
            last_user_agent=request.headers.get("User-Agent"),
            allowed_lab_unit_ids=_ints_to_csv(scope["allowed_lab_unit_ids"]),
            allowed_disease_ids=_ints_to_csv(scope["allowed_disease_ids"]),
            is_revoked=False,
            revoked_at=None,
            replaced_by_session_id=None,
        )
        db.add(mobile_session)
        db.flush()
    else:
        mobile_session.device_name = device_name
        mobile_session.refresh_token_hash = refresh_hash
        mobile_session.refresh_token_expires_at = now + lifetime
        mobile_session.last_used_at = now
        mobile_session.last_refreshed_at = now
        mobile_session.last_used_ip = request.remote_addr
        mobile_session.last_user_agent = request.headers.get("User-Agent")
        mobile_session.allowed_lab_unit_ids = _ints_to_csv(scope["allowed_lab_unit_ids"])
        mobile_session.allowed_disease_ids = _ints_to_csv(scope["allowed_disease_ids"])
        mobile_session.is_revoked = False
        mobile_session.revoked_at = None
        mobile_session.replaced_by_session_id = None
        db.flush()

    access_token = _encode_access_token(user, mobile_session, scope)
    return mobile_session, access_token, refresh_token, scope


def rotate_refresh_token(
    db,
    mobile_session: MobileAuthSession,
    user: User,
    refresh_lifetime: timedelta | None = None,
) -> tuple[str, str, dict[str, Any]]:
    scope = build_mobile_scope(db, user)
    now = utcnow()
    new_refresh_token = generate_refresh_token()
    mobile_session.refresh_token_hash = hash_refresh_token(new_refresh_token)
    mobile_session.refresh_token_expires_at = now + (refresh_lifetime or REFRESH_TOKEN_LIFETIME)
    mobile_session.last_refreshed_at = now
    mobile_session.last_used_at = now
    mobile_session.last_used_ip = request.remote_addr
    mobile_session.last_user_agent = request.headers.get("User-Agent")
    mobile_session.allowed_lab_unit_ids = _ints_to_csv(scope["allowed_lab_unit_ids"])
    mobile_session.allowed_disease_ids = _ints_to_csv(scope["allowed_disease_ids"])
    db.flush()

    return _encode_access_token(user, mobile_session, scope), new_refresh_token, scope


def serialize_mobile_session(mobile_session: MobileAuthSession) -> dict[str, Any]:
    return {
        "id": mobile_session.id,
        "device_id": mobile_session.device_id,
        "device_name": mobile_session.device_name,
        "created_at": mobile_session.created_at.isoformat(),
        "updated_at": mobile_session.updated_at.isoformat(),
        "last_used_at": mobile_session.last_used_at.isoformat(),
        "refresh_token_expires_at": mobile_session.refresh_token_expires_at.isoformat(),
        "allowed_lab_unit_ids": _csv_to_ints(mobile_session.allowed_lab_unit_ids),
        "allowed_disease_ids": _csv_to_ints(mobile_session.allowed_disease_ids),
        "is_revoked": mobile_session.is_revoked,
    }


def find_session_by_refresh_token(db, refresh_token: str) -> MobileAuthSession | None:
    refresh_hash = hash_refresh_token(refresh_token)
    return db.execute(
        select(MobileAuthSession)
        .options(selectinload(MobileAuthSession.user))
        .where(MobileAuthSession.refresh_token_hash == refresh_hash)
    ).scalar_one_or_none()


def validate_mobile_session(mobile_session: MobileAuthSession | None) -> bool:
    if mobile_session is None:
        return False
    if mobile_session.is_revoked:
        return False
    if mobile_session.refresh_token_expires_at <= utcnow():
        return False
    if not mobile_session.user or not mobile_session.user.is_active:
        return False
    return True


def revoke_mobile_session(db, mobile_session: MobileAuthSession, reason: str | None = None) -> None:
    mobile_session.is_revoked = True
    mobile_session.revoked_at = utcnow()
    # The reason is read back on the displaced device's next request so it can
    # explain what happened instead of showing a bare authentication failure.
    mobile_session.revoked_reason = reason
    db.flush()


def mobile_auth_response(
    user: User,
    access_token: str,
    refresh_token: str,
    scope: dict[str, Any],
    mobile_session: MobileAuthSession | None = None,
) -> dict[str, Any]:
    # Refresh lifetime now varies by device kind, so report the session's real
    # expiry. Reporting the 30-day default would make a shared device schedule
    # its refresh long after the token had already expired.
    if mobile_session is not None:
        refresh_expires_in = max(0, round((mobile_session.refresh_token_expires_at - utcnow()).total_seconds()))
    else:
        refresh_expires_in = int(REFRESH_TOKEN_LIFETIME.total_seconds())
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        "refresh_expires_in": refresh_expires_in,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "hospital_id": user.hospital_id,
        },
        "context": {
            "hospital": scope["hospital"],
            "lab_units": scope["lab_units"],
            "allowed_disease_ids": scope["allowed_disease_ids"],
            "roles": scope["roles"],
        },
        "_links": {
            "context": {"href": "/api/mobile/v1/context/me"},
            "sessions": {"href": "/api/mobile/v1/sessions"},
            "upload_profiles": {"href": "/api/mobile/v1/upload-options"},
            "refresh": {"href": "/api/mobile/v1/auth/refresh", "method": "POST"},
            "logout": {"href": "/api/mobile/v1/auth/logout", "method": "POST"},
        },
    }


def encode_access_token(user: User, mobile_session: MobileAuthSession, scope: dict[str, Any]) -> str:
    """Public entry point for minting an access token on an existing session (re-authentication)."""
    return _encode_access_token(user, mobile_session, scope)
