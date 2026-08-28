"""Request-local identity and relationship context for authorization checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from flask import g, has_request_context
from sqlalchemy.orm import Session


_REQUEST_CACHE_ATTR = "_lean_authz_context"


@dataclass
class AccessContext:
    """Authoritative actor facts plus a request-local lookup cache."""

    db: Session
    user_id: int
    active: bool
    hospital_id: int | None
    global_roles: frozenset[str]
    assigned_lab_unit_ids: frozenset[int]
    cache: dict[tuple[Any, ...], Any] = field(default_factory=dict)

    def has_any_global_role(self, roles: frozenset[str]) -> bool:
        return self.active and bool(self.global_roles & roles)


def access_context(db: Session, user: Any) -> AccessContext:
    """Build one context from server-side user state and cache it per request."""

    user_id = int(getattr(user, "id"))
    if has_request_context():
        cached = getattr(g, _REQUEST_CACHE_ATTR, None)
        if cached is not None and cached.user_id == user_id and cached.db is db:
            return cached

    context = AccessContext(
        db=db,
        user_id=user_id,
        active=bool(getattr(user, "is_active", False)),
        hospital_id=(
            int(user.hospital_id)
            if getattr(user, "hospital_id", None) is not None
            else None
        ),
        global_roles=frozenset(
            str(role.name).strip().lower()
            for role in (getattr(user, "roles", None) or ())
            if getattr(role, "name", None)
        ),
        assigned_lab_unit_ids=frozenset(
            int(lab.id)
            for lab in (getattr(user, "lab_units", None) or ())
            if getattr(lab, "id", None) is not None
        ),
    )
    if has_request_context():
        setattr(g, _REQUEST_CACHE_ATTR, context)
    return context


def clear_access_context() -> None:
    """Drop request-local facts after an authorization relationship mutation."""

    if has_request_context() and hasattr(g, _REQUEST_CACHE_ATTR):
        delattr(g, _REQUEST_CACHE_ATTR)
