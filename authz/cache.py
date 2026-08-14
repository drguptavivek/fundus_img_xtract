"""Redis-backed authorization decision caching and commit-safe invalidation."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app_cache import cache
from authz.telemetry import record_authorization_cache_error
from authz.types import AuthzDecision, GrantSource, ResourceRef


AUTHORIZATION_CACHE_TTL_SECONDS = 15 * 60
_PENDING_USER_IDS = "authz_pending_user_ids"
_PENDING_PROJECT_IDS = "authz_pending_project_ids"
_PENDING_HOSPITAL_IDS = "authz_pending_hospital_ids"


def get_cached_decision(
    *, user_id: int, action: str, resource: ResourceRef
) -> AuthzDecision | None:
    """Return a valid cached decision, or ``None`` on miss or cache failure.

    ``None`` means the caller must evaluate policy from persisted grants.  A
    Redis outage therefore fails over to the database and never grants access.
    """
    try:
        payload = cache.get(_decision_key(user_id=user_id, action=action, resource=resource))
    except Exception as exc:
        record_authorization_cache_error(operation="get_decision", error=exc)
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("allowed"), bool):
        return None
    source = payload.get("grant_source")
    try:
        grant_source = GrantSource(source) if source else None
    except ValueError:
        return None
    return AuthzDecision(
        allowed=payload["allowed"],
        action=action,
        reason=str(payload.get("reason", "allowed" if payload["allowed"] else "denied")),
        grant_source=grant_source,
    )


def set_cached_decision(
    *, user_id: int, action: str, resource: ResourceRef, decision: AuthzDecision
) -> None:
    """Cache one allow or deny decision for the shared 15-minute TTL."""
    try:
        cache.set(
            _decision_key(user_id=user_id, action=action, resource=resource),
            {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "grant_source": decision.grant_source.value if decision.grant_source else None,
            },
            timeout=AUTHORIZATION_CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        record_authorization_cache_error(operation="set_decision", error=exc)


def get_hmac_validation(
    *, token_hash: str, media_uuid: str, hospital_id: int, expires: int
) -> bool:
    """Return whether the exact signed-media credential was validated earlier."""
    try:
        return cache.get(
            _hmac_key(
                token_hash=token_hash,
                media_uuid=media_uuid,
                hospital_id=hospital_id,
                expires=expires,
            )
        ) is True
    except Exception as exc:
        record_authorization_cache_error(operation="get_hmac", error=exc)
        return False


def set_hmac_validation(
    *, token_hash: str, media_uuid: str, hospital_id: int, expires: int
) -> None:
    """Cache successful HMAC validation no longer than its remaining lifetime."""
    remaining = expires - int(time.time())
    if remaining <= 0:
        return
    try:
        cache.set(
            _hmac_key(
                token_hash=token_hash,
                media_uuid=media_uuid,
                hospital_id=hospital_id,
                expires=expires,
            ),
            True,
            timeout=min(AUTHORIZATION_CACHE_TTL_SECONDS, remaining),
        )
    except Exception as exc:
        record_authorization_cache_error(operation="set_hmac", error=exc)


def token_digest(token: str) -> str:
    """Return a one-way token digest suitable for a cache key component."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def schedule_authorization_invalidation(
    db: Session,
    *,
    user_ids: Iterable[int] = (),
    project_ids: Iterable[int] = (),
    hospital_ids: Iterable[int] = (),
) -> None:
    """Queue user/project/hospital epoch bumps for the current transaction.

    Epochs are applied only by ``after_commit`` and discarded on rollback, so
    readers never observe invalidation for a mutation that did not persist.
    """
    db.info.setdefault(_PENDING_USER_IDS, set()).update(int(value) for value in user_ids if value)
    db.info.setdefault(_PENDING_PROJECT_IDS, set()).update(int(value) for value in project_ids if value)
    db.info.setdefault(_PENDING_HOSPITAL_IDS, set()).update(int(value) for value in hospital_ids if value)


def _decision_key(*, user_id: int, action: str, resource: ResourceRef) -> str:
    """Build an opaque decision key incorporating current authorization epochs."""
    cache_action = "media.image.view" if action == "media.thumbnail.view" else action
    project_id = resource.attr("project_id")
    payload = {
        "user_id": user_id,
        "action": cache_action,
        "resource_type": resource.type,
        "resource_id": resource.id,
        "project_id": project_id,
        "hospital_id": resource.attr("hospital_id"),
        "lab_unit_id": resource.attr("lab_unit_id"),
        "uploader_user_id": resource.attr("uploader_user_id"),
        "user_epoch": _epoch("user", user_id),
        "project_epoch": _epoch("project", project_id) if project_id else "0",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"authz:decision:v1:{digest}"


def _hmac_key(*, token_hash: str, media_uuid: str, hospital_id: int, expires: int) -> str:
    """Build the exact credential cache key with the hospital signing epoch."""
    epoch = _epoch("hospital-signing", hospital_id)
    return f"authz:hmac:v1:{hospital_id}:{epoch}:{media_uuid}:{expires}:{token_hash}"


def _epoch(kind: str, value: int | None) -> str:
    """Read an invalidation epoch, using a miss-safe sentinel during outages."""
    if value is None:
        return "0"
    try:
        epoch = cache.get(f"authz:epoch:{kind}:{value}")
    except Exception as exc:
        record_authorization_cache_error(operation="get_epoch", error=exc)
        return "cache-unavailable"
    return str(epoch) if epoch is not None else "0"


def _bump_epoch(kind: str, value: int) -> None:
    """Replace one epoch so existing derived cache keys become unreachable."""
    try:
        cache.set(
            f"authz:epoch:{kind}:{value}",
            str(time.time_ns()),
            timeout=0,
        )
    except Exception as exc:
        record_authorization_cache_error(operation="set_epoch", error=exc)


@event.listens_for(Session, "before_flush")
def _collect_authorization_changes(db: Session, _flush_context: Any, _instances: Any) -> None:
    """Collect grant-bearing ORM changes without invalidating before commit."""
    user_ids: set[int] = set()
    project_ids: set[int] = set()
    hospital_ids: set[int] = set()
    relevant = db.new.union(db.dirty).union(db.deleted)
    for row in relevant:
        name = type(row).__name__
        if name == "User":
            user_ids.add(getattr(row, "id", 0) or 0)
        elif name in {"UserRole", "UserDiseaseUnitRole", "ProjectGraderAllocation"}:
            user_ids.add(getattr(row, "user_id", 0) or 0)
            project_ids.add(getattr(row, "project_id", 0) or 0)
        elif name in {"ProjectRoleGrant", "ProjectEncounterSetPermission", "ProjectInvestigator"}:
            user_ids.add(getattr(row, "user_id", 0) or 0)
            project_ids.add(getattr(row, "project_id", 0) or 0)
        elif name == "ProjectGradingAllocationPolicy":
            project_ids.add(getattr(row, "project_id", 0) or 0)
        elif name == "S3Config":
            hospital_ids.add(getattr(row, "hospital_id", 0) or 0)
    schedule_authorization_invalidation(
        db,
        user_ids=user_ids,
        project_ids=project_ids,
        hospital_ids=hospital_ids,
    )


@event.listens_for(Session, "after_commit")
def _apply_authorization_changes(db: Session) -> None:
    """Apply queued epoch bumps after a successful transaction commit."""
    for user_id in db.info.pop(_PENDING_USER_IDS, set()):
        _bump_epoch("user", user_id)
        try:
            cache.delete(f"auth:user:{user_id}")
            cache.delete(f"grading-allocation:eligibility:v1:user:{user_id}")
        except Exception as exc:
            record_authorization_cache_error(operation="delete_user_caches", error=exc)
    for project_id in db.info.pop(_PENDING_PROJECT_IDS, set()):
        _bump_epoch("project", project_id)
    for hospital_id in db.info.pop(_PENDING_HOSPITAL_IDS, set()):
        _bump_epoch("hospital-signing", hospital_id)


@event.listens_for(Session, "after_rollback")
def _discard_authorization_changes(db: Session) -> None:
    """Discard queued invalidations when the transaction rolls back."""
    db.info.pop(_PENDING_USER_IDS, None)
    db.info.pop(_PENDING_PROJECT_IDS, None)
    db.info.pop(_PENDING_HOSPITAL_IDS, None)
