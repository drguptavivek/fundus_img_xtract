"""Device enrolment, the login-time device gate, and per-device session policy.

``device_id`` arrives from the client and is therefore untrusted on its own. A
device becomes usable only once an administrator issues a single-use enrolment
code and the device redeems it, which is what stops leaked credentials alone
from reaching the API from an arbitrary handset.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from auth.mobile_tokens import _token_hash_secret
from auth.roles import FIELD_ROLE_NAMES
from auth.utils import utcnow
from utils.log_sanitize import sanitize_log_value

from .exceptions import (
    DeviceBlocked,
    DeviceNotEnrolled,
    DevicePendingApproval,
    EnrolmentCodeInvalid,
)
from .models import MobileDevice, MobileDeviceEnrolmentCode

logger = logging.getLogger("mobile_devices")

ENROLMENT_CODE_LIFETIME = timedelta(minutes=30)

# Refresh lifetimes by device kind. A shared camp device is handed between staff,
# so its window is deliberately short; a legacy upload-only session keeps the
# original 30 days so existing uploaders are not disrupted.
REFRESH_LIFETIME_SHARED = timedelta(hours=24)
REFRESH_LIFETIME_PERSONAL_FIELD = timedelta(days=7)
REFRESH_LIFETIME_DEFAULT = timedelta(days=30)

# One credential in use on one device at a time for field staff. No
# authentication factor detects credential sharing; capping concurrency does.
MAX_SESSIONS_FIELD_ROLE = 1
MAX_SESSIONS_DEFAULT = 2


@dataclass(frozen=True)
class IssuedEnrolmentCode:
    """The plaintext code is returned once and never stored."""

    code: str
    expires_at: datetime
    user_id: int
    device_kind: str


def hash_enrolment_code(code: str) -> str:
    return hmac.new(_token_hash_secret(), code.strip().upper().encode("utf-8"), hashlib.sha256).hexdigest()


def generate_enrolment_code() -> str:
    """Return a short, human-transcribable code.

    Field staff read this off a screen or a phone call, so it avoids characters
    that are easily confused when spoken or typed.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def issue_enrolment_code(
    db,
    *,
    user_id: int,
    issued_by_user_id: int,
    device_kind: str = "personal",
    label: str | None = None,
) -> IssuedEnrolmentCode:
    if device_kind not in {"personal", "shared"}:
        raise EnrolmentCodeInvalid("device_kind must be 'personal' or 'shared'.")
    code = generate_enrolment_code()
    expires_at = utcnow() + ENROLMENT_CODE_LIFETIME
    db.add(
        MobileDeviceEnrolmentCode(
            user_id=user_id,
            code_hash=hash_enrolment_code(code),
            device_kind=device_kind,
            label=label,
            expires_at=expires_at,
            issued_by_user_id=issued_by_user_id,
        )
    )
    db.flush()
    logger.info(
        "Device enrolment code issued user_id=%s issued_by=%s kind=%s",
        sanitize_log_value(user_id),
        sanitize_log_value(issued_by_user_id),
        sanitize_log_value(device_kind),
    )
    return IssuedEnrolmentCode(code=code, expires_at=expires_at, user_id=user_id, device_kind=device_kind)


def redeem_enrolment_code(
    db,
    *,
    user_id: int,
    code: str,
    device_id: str,
    label: str | None = None,
    platform: str | None = None,
) -> MobileDevice:
    """Consume a code and return the approved device row.

    The code is bound to ``user_id``, so redeeming it for another account fails
    even if the code itself is valid.
    """
    if not code or not device_id:
        raise EnrolmentCodeInvalid("An enrolment code and device_id are required.")

    row = db.execute(
        select(MobileDeviceEnrolmentCode)
        .where(MobileDeviceEnrolmentCode.code_hash == hash_enrolment_code(code))
        .with_for_update()
    ).scalar_one_or_none()
    now = utcnow()
    if row is None or row.used_at is not None or row.user_id != user_id or row.expires_at <= now:
        raise EnrolmentCodeInvalid()

    device = _get_device(db, user_id=user_id, device_id=device_id)
    if device is None:
        device = MobileDevice(user_id=user_id, device_id=device_id)
        db.add(device)
    if device.status == "blocked":
        # A blocked device must be unblocked by an administrator; redeeming a
        # fresh code must not be a way around that decision.
        raise DeviceBlocked()

    device.status = "approved"
    device.device_kind = row.device_kind
    device.label = label or row.label or device.label
    device.platform = platform or device.platform
    device.enrolled_at = now
    device.enrolled_by_user_id = row.issued_by_user_id

    row.used_at = now
    row.used_device_id = device_id
    db.flush()
    logger.info(
        "Device enrolled user_id=%s device_kind=%s",
        sanitize_log_value(user_id),
        sanitize_log_value(device.device_kind),
    )
    return device


WEB_PLATFORM = "web"


def ensure_web_device(db, *, user_id: int, device_id: str, label: str | None = None) -> MobileDevice | None:
    """Approve a browser (``platform == "web"``) device without an enrolment code.

    Product decision 2026-09-03: installed web apps use the same bearer tokens
    as phones but are not gated by device enrolment. Blocked devices stay
    blocked - an administrator's decision is never bypassed - and the switch
    ``MOBILE_WEB_DEVICES_AUTO_APPROVE`` turns the behaviour off wholesale.
    Returns the device row, or ``None`` when auto-approval is disabled.
    """
    from flask import current_app

    if not current_app.config.get("MOBILE_WEB_DEVICES_AUTO_APPROVE", True):
        return None
    device = _get_device(db, user_id=user_id, device_id=device_id)
    if device is None:
        device = MobileDevice(user_id=user_id, device_id=device_id)
        db.add(device)
    if device.status == "blocked":
        raise DeviceBlocked()
    if device.status != "approved":
        device.status = "approved"
        device.enrolled_at = utcnow()
    device.platform = WEB_PLATFORM
    device.label = label or device.label
    db.flush()
    return device


def require_approved_device(db, *, user_id: int, device_id: str) -> MobileDevice:
    """Raise unless this user has an approved row for this device."""
    device = _get_device(db, user_id=user_id, device_id=device_id)
    if device is None:
        raise DeviceNotEnrolled()
    if device.status == "blocked":
        raise DeviceBlocked()
    if device.status != "approved":
        raise DevicePendingApproval()
    return device


def touch_device(db, *, user_id: int, device_id: str) -> None:
    device = _get_device(db, user_id=user_id, device_id=device_id)
    if device is not None:
        device.last_seen_at = utcnow()


def set_device_status(db, *, user_id: int, device_id: str, status: str) -> MobileDevice | None:
    if status not in {"pending", "approved", "blocked"}:
        raise EnrolmentCodeInvalid("Unknown device status.")
    device = _get_device(db, user_id=user_id, device_id=device_id)
    if device is None:
        return None
    device.status = status
    device.blocked_at = utcnow() if status == "blocked" else None
    db.flush()
    return device


def list_user_devices(db, *, user_id: int) -> list[MobileDevice]:
    return list(
        db.execute(
            select(MobileDevice)
            .where(MobileDevice.user_id == user_id)
            .order_by(MobileDevice.created_at.desc())
        ).scalars()
    )


def refresh_lifetime_for(device: MobileDevice | None, *, user) -> timedelta:
    """Pick the refresh window from device kind and whether the user is field staff."""
    if device is None:
        return REFRESH_LIFETIME_DEFAULT
    if device.device_kind == "shared":
        return REFRESH_LIFETIME_SHARED
    if is_field_user(user):
        return REFRESH_LIFETIME_PERSONAL_FIELD
    return REFRESH_LIFETIME_DEFAULT


def max_active_sessions_for(user) -> int:
    return MAX_SESSIONS_FIELD_ROLE if is_field_user(user) else MAX_SESSIONS_DEFAULT


def is_field_user(user) -> bool:
    if user is None:
        return False
    return bool(user.has_role(*FIELD_ROLE_NAMES))


def _get_device(db, *, user_id: int, device_id: str) -> MobileDevice | None:
    return db.execute(
        select(MobileDevice).where(
            MobileDevice.user_id == user_id,
            MobileDevice.device_id == device_id,
        )
    ).scalar_one_or_none()
