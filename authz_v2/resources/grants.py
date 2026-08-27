"""Server-resolved grant-administration targets."""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import false

from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import ScopeType
from authz_v2.repositories.grants import GrantRepository
from authz_v2.resources.references import is_positive_int
from authz_v2.resources.registry import ResourceAdapter, ResourceTarget
from models import User


@dataclass(frozen=True)
class GrantTargetRef:
    """Internal reference whose exact target and lineage are always reloaded."""

    user_id: int
    scope_type: ScopeType
    scope_id: int | None


def resolve_grant_target(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, GrantTargetRef):
        return None
    if not is_positive_int(reference.user_id):
        return None
    if reference.scope_type is ScopeType.SYSTEM:
        if reference.scope_id is not None:
            return None
    elif not is_positive_int(reference.scope_id):
        return None
    user = db.get(User, reference.user_id)
    if user is None:
        return None
    scope = GrantRepository(db).resolve_scope(
        ScopeDTO(reference.scope_type, reference.scope_id)
    )
    if scope is None:
        return None
    resource_id = f"{user.id}:{scope.scope_type.value}:{scope.scope_id or 'system'}"
    return ResourceTarget(
        (user, scope),
        ResourceContextDTO(
            "grant_target",
            resource_id,
            scope,
            state={"domain_valid": bool(user.is_active)},
            resolved=True,
        ),
    )


def deny_grant_target_listing(_db, _principal, _action, _grants, query):
    return query.where(false())


def grant_target_facts(_db, _principal, _action, target, facts):
    user, _scope = target.value
    return replace(facts, domain_valid=bool(user.is_active))


GRANT_TARGET_ADAPTER = ResourceAdapter(
    "grant_target",
    resolve_grant_target,
    deny_grant_target_listing,
    grant_target_facts,
)
