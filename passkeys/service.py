"""Passkey registration and assertion ceremonies (server side).

Challenge state between the two halves of a ceremony is kept server-side in
Redis (5-minute TTL) keyed by an opaque ``challenge_id``; when Redis is not
configured (tests, single-process dev) an in-process store is used.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fido2.server import Fido2Server
from fido2.webauthn import (
    AttestedCredentialData,
    AuthenticatorAttachment,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialUserEntity,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from flask import current_app, request
from sqlalchemy import select

from auth.utils import utcnow
from models import User
from utils.log_sanitize import sanitize_log_value

from .models import MobilePasskey

logger = logging.getLogger("passkeys")

CHALLENGE_TTL_SECONDS = 300
MAX_PASSKEYS_PER_USER = 10


class PasskeyError(ValueError):
    def __init__(self, message: str, *, code: str = "passkey_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PasskeyDTO:
    id: int
    label: str | None
    created_at: str
    last_used_at: str | None
    device_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "device_id": self.device_id,
        }


# --------------------------------------------------------------------------- #
# Challenge state
# --------------------------------------------------------------------------- #

_memory_store: dict[str, tuple[float, str]] = {}


def _redis():
    url = current_app.config.get("REDIS_URL") or current_app.config.get("CELERY_BROKER_URL")
    if not url:
        return None
    try:
        import redis

        client = redis.Redis.from_url(url)
        client.ping()
        return client
    except Exception:  # noqa: BLE001 - fall back to the in-process store
        return None


def _store_state(kind: str, state: dict[str, Any], user_id: int) -> str:
    challenge_id = secrets.token_urlsafe(24)
    payload = json.dumps({"kind": kind, "user_id": user_id, "state": state})
    client = _redis()
    key = f"passkey:{challenge_id}"
    if client is not None:
        client.setex(key, CHALLENGE_TTL_SECONDS, payload)
    else:
        now = time.time()
        for stale in [k for k, (expires, _) in _memory_store.items() if expires < now]:
            _memory_store.pop(stale, None)
        _memory_store[key] = (now + CHALLENGE_TTL_SECONDS, payload)
    return challenge_id


def _pop_state(kind: str, challenge_id: str, user_id: int) -> dict[str, Any]:
    key = f"passkey:{challenge_id or ''}"
    client = _redis()
    raw = None
    if client is not None:
        raw = client.get(key)
        if raw is not None:
            client.delete(key)
    else:
        entry = _memory_store.pop(key, None)
        if entry and entry[0] >= time.time():
            raw = entry[1]
    if raw is None:
        raise PasskeyError("This passkey request has expired. Try again.", code="challenge_expired")
    payload = json.loads(raw)
    if payload.get("kind") != kind or payload.get("user_id") != user_id:
        raise PasskeyError("This passkey request does not match.", code="challenge_mismatch")
    return payload["state"]


# --------------------------------------------------------------------------- #
# Relying party
# --------------------------------------------------------------------------- #


def _rp_id() -> str:
    configured = current_app.config.get("WEBAUTHN_RP_ID")
    if configured:
        return configured
    return request.host.split(":", 1)[0]


def _origin() -> str:
    configured = current_app.config.get("WEBAUTHN_ORIGIN")
    return configured or f"{request.scheme}://{request.host}"


def _server() -> Fido2Server:
    rp = PublicKeyCredentialRpEntity(name=current_app.config.get("WEBAUTHN_RP_NAME", "Eye Image Manager"), id=_rp_id())
    expected_origin = _origin()
    return Fido2Server(rp, verify_origin=lambda origin: origin == expected_origin)


def _user_entity(user: User) -> PublicKeyCredentialUserEntity:
    return PublicKeyCredentialUserEntity(
        name=user.username,
        id=str(user.id).encode("utf-8"),
        display_name=user.full_name or user.username,
    )


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _credentials_for(db, user_id: int) -> list[MobilePasskey]:
    return list(
        db.execute(
            select(MobilePasskey).where(MobilePasskey.user_id == user_id).order_by(MobilePasskey.id)
        ).scalars()
    )


def _attested(row: MobilePasskey) -> AttestedCredentialData:
    return AttestedCredentialData.create(
        aaguid=_b64url_decode(row.aaguid) if row.aaguid else b"\x00" * 16,
        credential_id=_b64url_decode(row.credential_id),
        public_key=json.loads(row.public_key.decode("utf-8")) if row.public_key[:1] == b"{" else _cose_from_bytes(row.public_key),
    )


def _cose_from_bytes(raw: bytes):
    from fido2.cose import CoseKey
    from fido2 import cbor

    return CoseKey.parse(cbor.decode(raw))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def list_passkeys(db, *, user_id: int) -> list[PasskeyDTO]:
    return [
        PasskeyDTO(
            id=row.id,
            label=row.label,
            created_at=row.created_at.isoformat(),
            last_used_at=row.last_used_at.isoformat() if row.last_used_at else None,
            device_id=row.device_id,
        )
        for row in _credentials_for(db, user_id)
    ]


def begin_registration(db, *, user: User) -> dict[str, Any]:
    """Options for ``navigator.credentials.create`` plus a challenge id."""
    existing = _credentials_for(db, user.id)
    if len(existing) >= MAX_PASSKEYS_PER_USER:
        raise PasskeyError("Too many passkeys on this account.", code="too_many_passkeys")
    options, state = _server().register_begin(
        _user_entity(user),
        [_attested(row) for row in existing],
        user_verification=UserVerificationRequirement.REQUIRED,
        authenticator_attachment=AuthenticatorAttachment.PLATFORM,
        resident_key_requirement=ResidentKeyRequirement.PREFERRED,
    )
    challenge_id = _store_state("register", state, user.id)
    return {"challenge_id": challenge_id, "options": dict(options)}


def complete_registration(db, *, user: User, challenge_id: str, credential: dict[str, Any],
                          label: str | None, device_id: str | None) -> PasskeyDTO:
    state = _pop_state("register", challenge_id, user.id)
    try:
        auth_data = _server().register_complete(state, credential)
    except Exception as exc:  # noqa: BLE001 - fido2 raises assorted ValueErrors
        logger.warning("Passkey registration failed user_id=%s: %s", sanitize_log_value(user.id), sanitize_log_value(str(exc)))
        raise PasskeyError("The passkey could not be verified.", code="registration_failed") from exc
    credential_data = auth_data.credential_data
    if credential_data is None:
        raise PasskeyError("The passkey could not be verified.", code="registration_failed")
    from fido2 import cbor

    row = MobilePasskey(
        user_id=user.id,
        credential_id=_b64url_encode(credential_data.credential_id),
        public_key=cbor.encode(dict(credential_data.public_key)),
        sign_count=auth_data.counter,
        aaguid=_b64url_encode(bytes(credential_data.aaguid)),
        transports=",".join((credential.get("response") or {}).get("transports") or []) or None,
        label=(label or "").strip()[:255] or None,
        device_id=(device_id or "").strip()[:128] or None,
    )
    db.add(row)
    db.flush()
    logger.info("Passkey registered user_id=%s passkey_id=%s", sanitize_log_value(user.id), row.id)
    return list_passkeys(db, user_id=user.id)[-1]


def begin_assertion(db, *, user: User) -> dict[str, Any]:
    """Options for ``navigator.credentials.get`` restricted to this user's passkeys."""
    existing = _credentials_for(db, user.id)
    if not existing:
        raise PasskeyError("No passkey is registered for this account.", code="no_passkey", status_code=404)
    options, state = _server().authenticate_begin(
        [_attested(row) for row in existing],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_id = _store_state("assert", state, user.id)
    return {"challenge_id": challenge_id, "options": dict(options)}


def complete_assertion(db, *, user: User, challenge_id: str, credential: dict[str, Any]) -> MobilePasskey:
    state = _pop_state("assert", challenge_id, user.id)
    existing = _credentials_for(db, user.id)
    try:
        result = _server().authenticate_complete(state, [_attested(row) for row in existing], credential)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Passkey assertion failed user_id=%s: %s", sanitize_log_value(user.id), sanitize_log_value(str(exc)))
        raise PasskeyError("The passkey could not be verified.", code="assertion_failed", status_code=401) from exc
    used_id = _b64url_encode(result.credential_id)
    row = next((item for item in existing if item.credential_id == used_id), None)
    if row is None:
        raise PasskeyError("The passkey could not be verified.", code="assertion_failed", status_code=401)
    row.last_used_at = utcnow()
    db.flush()
    return row


def delete_passkey(db, *, user_id: int, passkey_id: int) -> bool:
    row = db.execute(
        select(MobilePasskey).where(MobilePasskey.id == passkey_id, MobilePasskey.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
