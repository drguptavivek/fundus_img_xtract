"""Security boundaries and audit records for temporary user impersonation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from models import SensitiveOperationAudit, User


class ImpersonationError(Exception):
    """A safe-to-display impersonation validation error."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ImpersonationResult:
    original_user: User
    effective_user: User


def _load_user(db, user_id: int) -> User | None:
    return db.execute(
        select(User)
        .options(joinedload(User.roles), joinedload(User.hospital))
        .where(User.id == user_id)
    ).unique().scalar_one_or_none()


def _add_audit(
    db,
    *,
    admin_user_id: int,
    status: str,
    target: User,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    row = SensitiveOperationAudit(
        user_id=admin_user_id,
        operation_type="user_impersonation",
        status=status,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    row.set_request_details({"target_user_id": target.id, "target_username": target.username})
    db.add(row)


def start_impersonation(
    db,
    *,
    actor_user_id: int,
    target_user_id: int,
    already_impersonating: bool,
    ip_address: str | None,
    user_agent: str | None,
) -> ImpersonationResult:
    actor = _load_user(db, actor_user_id)
    if actor is None or not actor.is_active or not actor.has_role("admin"):
        raise ImpersonationError("Only an active system administrator can impersonate users.", status_code=403)
    if already_impersonating:
        raise ImpersonationError("End the current impersonation session before starting another.", status_code=409)
    if actor.id == target_user_id:
        raise ImpersonationError("You cannot impersonate your own account.")

    target = _load_user(db, target_user_id)
    if target is None:
        raise ImpersonationError("User not found.", status_code=404)
    if not target.is_active:
        raise ImpersonationError("Inactive users cannot be impersonated.", status_code=409)
    if target.has_role("admin"):
        raise ImpersonationError("Administrator accounts cannot be impersonated.", status_code=403)

    _add_audit(
        db,
        admin_user_id=actor.id,
        status="started",
        target=target,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ImpersonationResult(original_user=actor, effective_user=target)


def stop_impersonation(
    db,
    *,
    original_user_id: int,
    effective_user_id: int,
    ip_address: str | None,
    user_agent: str | None,
) -> ImpersonationResult:
    original = _load_user(db, original_user_id)
    if original is None or not original.is_active or not original.has_role("admin"):
        raise ImpersonationError(
            "The original administrator account is no longer authorized.",
            status_code=403,
        )
    target = _load_user(db, effective_user_id)
    if target is None:
        raise ImpersonationError("The impersonated user no longer exists.", status_code=409)

    _add_audit(
        db,
        admin_user_id=original.id,
        status="stopped",
        target=target,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return ImpersonationResult(original_user=original, effective_user=target)
