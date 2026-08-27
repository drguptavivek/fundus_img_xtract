"""Atomic verification and consumption of one-use signed credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest

from sqlalchemy import select

from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.domain.models import PasswordResetCredential


def consume_password_reset_credential(
    db, credential_id: int, raw_token: str, *, consumed_at: datetime | None = None
) -> PasswordResetCredential:
    """Lock, verify, and mark a reset credential consumed in the caller transaction."""
    credential = db.execute(
        select(PasswordResetCredential)
        .where(PasswordResetCredential.id == credential_id)
        .with_for_update()
    ).scalar_one_or_none()
    now = consumed_at or datetime.now(UTC)
    supplied_hash = sha256(raw_token.encode("utf-8")).hexdigest()
    valid = bool(
        credential is not None
        and credential.consumed_at is None
        and credential.expires_at > now
        and compare_digest(supplied_hash, credential.token_hash)
    )
    if not valid:
        raise AuthorizationError(DenialCode.NOT_AUTHORIZED)
    credential.consumed_at = now
    db.flush()
    return credential
