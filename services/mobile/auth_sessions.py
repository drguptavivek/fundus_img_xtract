from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import jwt
import redis
from flask import request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from auth.mobile_tokens import (
    find_session_by_refresh_token,
    mobile_auth_response,
    revoke_mobile_session,
    rotate_refresh_token,
    serialize_mobile_session,
    validate_mobile_session,
)
from auth.mobile_tokens import create_mobile_session as create_token_session
from auth.mobile_tokens import ACCESS_TOKEN_LIFETIME
from auth.routes import (
    MAX_FAILS_PER_IP,
    MAX_FAILS_PER_USERNAME,
    _is_ip_locked,
    _lock_ip,
    _lock_user,
    _recent_failed_by_ip,
    _recent_failed_by_username,
    _record_attempt,
)
from auth.security import verify_password
from auth.utils import utcnow
from mobile_devices.exceptions import DeviceBlocked, MobileDeviceError
from mobile_devices.service import (
    is_field_user,
    max_active_sessions_for,
    redeem_enrolment_code,
    refresh_lifetime_for,
    require_approved_device,
    touch_device,
    WEB_PLATFORM,
    ensure_web_device,
)
from models import MobileAuthSession, User
from utils.log_sanitize import sanitize_log_value
from utils.redis_connection import build_redis_url

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None
_REVOKED_JTI_PREFIX = "fim:mobile:revoked_jti:"
MAX_ACTIVE_MOBILE_SESSIONS_PER_USER = 2


@dataclass(frozen=True)
class MobileLoginRequest:
    username: str
    password: str
    device_id: str
    device_name: str
    ip_address: str
    # Supplied only on a device's first sign-in. Redeeming the code during login
    # keeps enrolment to one screen and verifies the password exactly once.
    enrolment_code: str = ""
    platform: str | None = None


@dataclass(frozen=True)
class RefreshTokenRequest:
    refresh_token: str
    device_id: str


@dataclass(frozen=True)
class AccessTokenContext:
    claims: dict
    session: MobileAuthSession
    user: User
    # Seconds since this session's previous request, measured before this
    # request refreshed ``last_used_at``; the grading gate turns it into a
    # re-authentication demand after 30 idle minutes.
    idle_seconds: float = 0.0
    authenticated_at: datetime | None = None


# Endpoints whose requests are machine-generated and never count as activity.
BACKGROUND_ENDPOINTS = frozenset({"fundus_api.heartbeat_workbench_session"})


class MobileAuthError(ValueError):
    def __init__(self, message: str, *, code: str = "mobile_auth_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def login_mobile_user(db, login_request: MobileLoginRequest) -> dict:
    username = login_request.username
    ip = login_request.ip_address

    ip_locked, _ = _is_ip_locked(db, ip)
    if ip_locked:
        raise MobileAuthError("Too many attempts. IP is temporarily locked.", code="ip_locked", status_code=403)

    recent_user_fails = _recent_failed_by_username(db, username)
    if recent_user_fails >= MAX_FAILS_PER_USERNAME:
        user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
        if user:
            _lock_user(db, user)
        _record_attempt(db, username, ip, success=False)
        raise MobileAuthError("Too many attempts. User is temporarily locked.", code="user_locked", status_code=403)

    recent_ip_fails = _recent_failed_by_ip(db, ip)
    if recent_ip_fails >= MAX_FAILS_PER_IP:
        _lock_ip(db, ip)
        _record_attempt(db, username, ip, success=False)
        raise MobileAuthError("Too many attempts. IP is temporarily locked.", code="ip_locked", status_code=403)

    user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
    if user and user.is_locked_until:
        locked_until = user.is_locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=utcnow().tzinfo)
        if locked_until > utcnow():
            _record_attempt(db, username, ip, success=False)
            raise MobileAuthError("Too many attempts. User is temporarily locked.", code="user_locked", status_code=403)

    if user is None or not user.is_active or not verify_password(user.password_hash, login_request.password):
        _record_attempt(db, username, ip, success=False)
        if user and _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME:
            _lock_user(db, user)
        if _recent_failed_by_ip(db, ip) >= MAX_FAILS_PER_IP:
            _lock_ip(db, ip)
        raise MobileAuthError("Invalid username or password", code="invalid_credentials", status_code=401)

    # Enrol before gating, so a first sign-in with a valid code succeeds in one
    # request. A bad code fails here rather than falling through to the gate.
    if login_request.enrolment_code:
        try:
            redeem_enrolment_code(
                db,
                user_id=user.id,
                code=login_request.enrolment_code,
                device_id=login_request.device_id,
                label=login_request.device_name,
                platform=login_request.platform,
            )
        except MobileDeviceError as exc:
            raise MobileAuthError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    return _open_mobile_session(db, user, login_request)


def _open_mobile_session(db, user: User, login_request: MobileLoginRequest) -> dict:
    """Everything after the credential check: device gate, token session,
    session limit, audit. Shared by the password and passkey sign-ins."""
    username = login_request.username
    ip = login_request.ip_address

    # Browsers (the grader PWA) carry the same tokens but skip enrolment: the
    # device row is created approved unless an administrator blocked it.
    if login_request.platform == WEB_PLATFORM and not login_request.enrolment_code:
        try:
            ensure_web_device(
                db,
                user_id=user.id,
                device_id=login_request.device_id,
                label=login_request.device_name,
            )
        except MobileDeviceError as exc:
            raise MobileAuthError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    # The device gate runs only after credentials verify, so an unenrolled-device
    # response can never be used to probe for valid usernames.
    #
    # A device refusal deliberately does NOT count as a failed attempt: the
    # password was correct, and counting it would let a field user lock their own
    # account by retrying while they wait for an administrator to approve the
    # device. Volume is already bounded by the login rate limit.
    try:
        device = require_approved_device(db, user_id=user.id, device_id=login_request.device_id)
    except MobileDeviceError as exc:
        logger.warning(
            "Mobile login refused for unapproved device user=%s reason=%s",
            sanitize_log_value(user.username),
            sanitize_log_value(exc.code),
        )
        raise MobileAuthError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    _require_revocation_store_for_field_user(user)

    _record_attempt(db, username, ip, success=True)
    mobile_session, access_token, refresh_token, scope = create_token_session(
        db,
        user,
        device_id=login_request.device_id,
        device_name=login_request.device_name,
        refresh_lifetime=refresh_lifetime_for(device, user=user),
    )
    touch_device(db, user_id=user.id, device_id=login_request.device_id)
    enforce_mobile_session_limit(
        db,
        user_id=user.id,
        current_session_id=mobile_session.id,
        max_active_sessions=max_active_sessions_for(user),
    )
    logger.info(
        "Mobile login successful user=%s device_id=%s",
        sanitize_log_value(user.username),
        sanitize_log_value(login_request.device_id),
    )
    return mobile_auth_response(user, access_token, refresh_token, scope, mobile_session)


def mobile_login_gate(db, *, username: str, ip: str) -> User | None:
    """Lockout checks shared by password and passkey sign-in.

    Raises the same ``MobileAuthError`` the password path does; returns the
    active user row or ``None`` (unknown / inactive - callers must answer
    identically to a missing credential so accounts cannot be enumerated).
    """
    ip_locked, _ = _is_ip_locked(db, ip)
    if ip_locked:
        raise MobileAuthError("Too many attempts. IP is temporarily locked.", code="ip_locked", status_code=403)
    if _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME:
        user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
        if user:
            _lock_user(db, user)
        _record_attempt(db, username, ip, success=False)
        raise MobileAuthError("Too many attempts. User is temporarily locked.", code="user_locked", status_code=403)
    if _recent_failed_by_ip(db, ip) >= MAX_FAILS_PER_IP:
        _lock_ip(db, ip)
        _record_attempt(db, username, ip, success=False)
        raise MobileAuthError("Too many attempts. IP is temporarily locked.", code="ip_locked", status_code=403)
    user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
    if user and user.is_locked_until:
        locked_until = user.is_locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=utcnow().tzinfo)
        if locked_until > utcnow():
            _record_attempt(db, username, ip, success=False)
            raise MobileAuthError("Too many attempts. User is temporarily locked.", code="user_locked", status_code=403)
    if user is None or not user.is_active:
        return None
    return user


def login_mobile_user_with_passkey(db, login_request: MobileLoginRequest, *, user: User) -> dict:
    """Open a mobile session for ``user`` after a verified passkey assertion."""
    return _open_mobile_session(db, user, login_request)


def _require_revocation_store_for_field_user(user) -> None:
    """Refuse a new field session when the token denylist is unreachable.

    Field sessions reach patient data, so losing the ability to revoke an issued
    access token before it expires is not an acceptable degradation. Existing
    sessions still validate against the database, which remains authoritative;
    only minting a *new* field session is blocked.
    """
    if not is_field_user(user):
        return
    client = _get_redis_client()
    if client is None:
        raise MobileAuthError(
            "Sign-in is temporarily unavailable. Please try again shortly.",
            code="revocation_store_unavailable",
            status_code=503,
        )
    try:
        client.ping()
    except redis.RedisError as exc:
        logger.error(
            "Refusing field mobile session because Redis is unavailable: %s",
            sanitize_log_value(exc),
        )
        raise MobileAuthError(
            "Sign-in is temporarily unavailable. Please try again shortly.",
            code="revocation_store_unavailable",
            status_code=503,
        ) from exc


def refresh_mobile_tokens(db, refresh_request: RefreshTokenRequest) -> dict:
    mobile_session = find_session_by_refresh_token(db, refresh_request.refresh_token)
    if not validate_mobile_session(mobile_session):
        raise MobileAuthError("Invalid refresh token", code="invalid_refresh_token", status_code=401)
    assert mobile_session is not None
    if mobile_session.device_id != refresh_request.device_id:
        raise MobileAuthError("Invalid device for refresh token", code="invalid_refresh_device", status_code=401)

    user = db.get(User, mobile_session.user_id)
    if user is None or not user.is_active:
        revoke_mobile_session(db, mobile_session)
        raise MobileAuthError("User is inactive", code="inactive_user", status_code=403)

    try:
        device = require_approved_device(db, user_id=user.id, device_id=mobile_session.device_id)
    except MobileDeviceError as exc:
        revoke_mobile_session(db, mobile_session)
        raise MobileAuthError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    access_token, new_refresh_token, scope = rotate_refresh_token(
        db, mobile_session, user, refresh_lifetime=refresh_lifetime_for(device, user=user)
    )
    return mobile_auth_response(user, access_token, new_refresh_token, scope, mobile_session)


def logout_mobile_session(db, *, refresh_token: str, access_claims: dict | None = None) -> None:
    mobile_session = find_session_by_refresh_token(db, refresh_token)
    if mobile_session is None:
        return
    revoke_mobile_session(db, mobile_session)
    _revoke_claims_jti(access_claims)


def mobile_sessions_collection(db, *, user_id: int, current_session_id: str | None) -> dict:
    return {
        "sessions": list_mobile_sessions(db, user_id=user_id, current_session_id=current_session_id),
        "_links": {
            "self": {"href": "/api/mobile/v1/sessions"},
            "context": {"href": "/api/mobile/v1/context/me"},
            "upload_profiles": {"href": "/api/mobile/v1/upload-options"},
            "refresh": {"href": "/api/mobile/v1/auth/refresh", "method": "POST"},
            "logout": {"href": "/api/mobile/v1/auth/logout", "method": "POST"},
        },
    }


def list_mobile_sessions(db, *, user_id: int, current_session_id: str | None) -> list[dict]:
    user = db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id)
    ).scalar_one_or_none()
    profile = _session_profile(user) if user else None
    sessions = db.execute(
        select(MobileAuthSession)
        .where(MobileAuthSession.user_id == user_id)
        .order_by(MobileAuthSession.created_at.desc())
    ).scalars().all()
    payload = []
    for item in sessions:
        payload.append(_serialize_session_item(item, current_session_id=current_session_id, profile=profile))
    return payload


def get_mobile_session_payload(db, *, user_id: int, session_id: str, current_session_id: str | None) -> dict | None:
    user = db.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id)
    ).scalar_one_or_none()
    item = db.execute(
        select(MobileAuthSession)
        .where(MobileAuthSession.id == session_id)
        .where(MobileAuthSession.user_id == user_id)
    ).scalar_one_or_none()
    if item is None:
        return None
    return _serialize_session_item(item, current_session_id=current_session_id, profile=_session_profile(user) if user else None)


def revoke_user_mobile_session(
    db,
    *,
    user_id: int,
    session_id: str,
    current_session_id: str | None,
    access_claims: dict | None = None,
) -> bool:
    mobile_session = db.execute(
        select(MobileAuthSession)
        .where(MobileAuthSession.id == session_id)
        .where(MobileAuthSession.user_id == user_id)
    ).scalar_one_or_none()
    if mobile_session is None:
        return False
    revoke_mobile_session(db, mobile_session)
    if session_id == current_session_id:
        _revoke_claims_jti(access_claims)
    return True


def enforce_mobile_session_limit(
    db,
    *,
    user_id: int,
    current_session_id: str,
    max_active_sessions: int = MAX_ACTIVE_MOBILE_SESSIONS_PER_USER,
) -> int:
    active_sessions = db.execute(
        select(MobileAuthSession)
        .where(MobileAuthSession.user_id == user_id)
        .where(MobileAuthSession.is_revoked == False)  # noqa: E712
        .order_by(MobileAuthSession.created_at.desc(), MobileAuthSession.last_used_at.desc())
    ).scalars().all()
    protected = [session for session in active_sessions if session.id == current_session_id]
    others = [session for session in active_sessions if session.id != current_session_id]
    keep_ids = {session.id for session in (protected + others)[:max_active_sessions]}

    revoked = 0
    for session in active_sessions:
        if session.id in keep_ids:
            continue
        revoke_mobile_session(db, session, reason="session_superseded")
        revoked += 1
    return revoked


def validate_access_session(db, claims: dict) -> AccessTokenContext:
    jti = claims.get("jti")
    if jti and is_access_jti_revoked(str(jti)):
        raise MobileAuthError("Token has been revoked", code="access_token_revoked", status_code=401)

    mobile_session_id = claims.get("mobile_session_id")
    if not mobile_session_id:
        raise MobileAuthError("Mobile session is invalid", code="invalid_mobile_session", status_code=401)

    mobile_session = db.execute(
        select(MobileAuthSession).where(MobileAuthSession.id == mobile_session_id)
    ).scalar_one_or_none()
    if mobile_session is None:
        raise MobileAuthError("Mobile session is invalid", code="invalid_mobile_session", status_code=401)
    if mobile_session.is_revoked:
        if mobile_session.revoked_reason == "session_superseded":
            raise MobileAuthError(
                "Signed in on another device. Only one active session is allowed.",
                code="session_superseded",
                status_code=401,
            )
        raise MobileAuthError("Mobile session is invalid", code="invalid_mobile_session", status_code=401)
    if mobile_session.refresh_token_expires_at <= utcnow():
        raise MobileAuthError("Mobile session expired", code="mobile_session_expired", status_code=401)

    user = db.get(User, mobile_session.user_id)
    if user is None or not user.is_active:
        raise MobileAuthError("User is inactive", code="inactive_user", status_code=403)

    # Re-check the device on every request: blocking a device must take effect at
    # the next call rather than when its access token happens to expire.
    try:
        require_approved_device(db, user_id=user.id, device_id=mobile_session.device_id)
    except MobileDeviceError as exc:
        raise MobileAuthError(exc.message, code=exc.code, status_code=exc.status_code) from exc

    now = utcnow()
    previous = mobile_session.last_used_at
    if previous is not None and previous.tzinfo is None:
        previous = previous.replace(tzinfo=now.tzinfo)
    idle_seconds = max(0.0, (now - previous).total_seconds()) if previous else 0.0
    # Automatic traffic (the workbench lease heartbeat) keeps a page alive but
    # is not the user doing anything; leaving last_used_at alone means the
    # 30-minute inactivity gate measures real interaction.
    if request.endpoint not in BACKGROUND_ENDPOINTS:
        mobile_session.last_used_at = now
    mobile_session.last_used_ip = request.remote_addr
    mobile_session.last_user_agent = request.headers.get("User-Agent")
    db.flush()
    return AccessTokenContext(
        claims=claims,
        session=mobile_session,
        user=user,
        idle_seconds=idle_seconds,
        authenticated_at=mobile_session.last_authenticated_at,
    )


def reauthenticate_mobile_session(db, *, context: AccessTokenContext, password: str, ip_address: str) -> dict:
    """Re-prove identity on an existing mobile session with the password.

    Issues a fresh access token whose ``auth_time`` is now; the refresh token
    is untouched. Failed attempts count toward the same lockouts as login.
    """
    user = context.user
    username = user.username
    if not password or not verify_password(user.password_hash, password):
        _record_attempt(db, username, ip_address, success=False)
        if _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME:
            _lock_user(db, user)
        raise MobileAuthError("Invalid password", code="invalid_credentials", status_code=401)
    return mark_reauthenticated(db, context=context, ip_address=ip_address, method="password")


def mark_reauthenticated(db, *, context: AccessTokenContext, ip_address: str, method: str) -> dict:
    """Record a successful identity proof and mint a fresh access token."""
    from auth.mobile_tokens import build_mobile_scope, encode_access_token

    mobile_session = context.session
    user = context.user
    now = utcnow()
    mobile_session.last_authenticated_at = now
    mobile_session.last_used_at = now
    db.flush()
    _record_attempt(db, user.username, ip_address, success=True)
    scope = build_mobile_scope(db, user)
    access_token = encode_access_token(user, mobile_session, scope)
    logger.info(
        "Mobile re-authentication user=%s method=%s device_id=%s",
        sanitize_log_value(user.username),
        sanitize_log_value(method),
        sanitize_log_value(mobile_session.device_id),
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        "auth_time": int(now.timestamp()),
        "method": method,
    }


def revoke_access_jti(jti: str, expires_at: datetime | int | float | None) -> None:
    if not jti or expires_at is None:
        return
    ttl_seconds = _ttl_seconds(expires_at)
    if ttl_seconds <= 0:
        return
    client = _get_redis_client()
    if client is None:
        logger.warning("Mobile access-token revocation skipped because Redis is unavailable")
        return
    try:
        client.setex(_revoked_jti_key(jti), ttl_seconds, "1")
    except redis.RedisError as exc:
        logger.error("Mobile access-token revocation write failed: %s", sanitize_log_value(exc))


def is_access_jti_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    client = _get_redis_client()
    if client is None:
        logger.warning("Mobile access-token revocation check skipped because Redis is unavailable")
        return False
    try:
        return client.get(_revoked_jti_key(jti)) == "1"
    except redis.RedisError as exc:
        logger.error("Mobile access-token revocation check failed: %s", sanitize_log_value(exc))
        return False


def decode_access_claims_without_revocation(token: str, jwt_secret: str) -> dict | None:
    try:
        claims = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    if claims.get("typ") and claims.get("typ") != "access":
        return None
    return claims


def _revoke_claims_jti(claims: dict | None) -> None:
    if not claims:
        return
    revoke_access_jti(str(claims.get("jti") or ""), claims.get("exp"))


def _ttl_seconds(expires_at: datetime | int | float) -> int:
    if isinstance(expires_at, datetime):
        return max(0, int((expires_at - utcnow()).total_seconds()))
    return max(0, int(float(expires_at) - utcnow().timestamp()))


def _get_redis_client() -> redis.Redis | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis.from_url(build_redis_url(), decode_responses=True)
    except redis.RedisError as exc:
        logger.error("Mobile auth Redis init failed: %s", sanitize_log_value(exc))
        _redis_client = None
    return _redis_client


def _revoked_jti_key(jti: str) -> str:
    return f"{_REVOKED_JTI_PREFIX}{jti}"


def _serialize_session_item(item: MobileAuthSession, *, current_session_id: str | None, profile: dict | None) -> dict:
    row = serialize_mobile_session(item)
    row["session_id"] = row.pop("id")
    row["is_current"] = item.id == current_session_id
    row["current"] = row["is_current"]
    row["revoked_at"] = item.revoked_at.isoformat() if item.revoked_at else None
    row["last_user_agent"] = item.last_user_agent
    row["last_used_ip"] = item.last_used_ip
    row["profile"] = profile
    row["_links"] = {"self": {"href": f"/api/mobile/v1/sessions/{item.id}"}}
    if not item.is_revoked:
        row["_links"]["revoke"] = {"href": f"/api/mobile/v1/sessions/{item.id}/revoke", "method": "POST"}
    return row


def _session_profile(user: User) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "hospital_id": user.hospital_id,
        "roles": sorted(role.name for role in (user.roles or [])),
    }
