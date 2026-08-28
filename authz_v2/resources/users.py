"""Authoritative user-resource resolver and SQL scoper."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import false

from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.principals import GrantSource, RelationshipEvidenceDTO
from authz_v2.core.roles import Role, ScopeType, may_delegate, role_accepts_scope
from authz_v2.repositories.grants import GrantRepository
from authz_v2.resources.references import UserCreationTargetRef, is_positive_int
from authz_v2.resources.registry import ResourceAdapter, ResourceTarget
from authz_v2.resources.scoping import admin_has_system_scope, resolve_scope
from models import Hospital, User


def resolve_user(db, resource_id: object) -> ResourceTarget | None:
    if not is_positive_int(resource_id):
        return None
    user = db.get(User, resource_id)
    if user is None:
        return None
    scope = resolve_scope(
        db,
        hospital_id=user.hospital_id,
        allow_system=user.hospital_id is None,
    )
    if scope is None:
        return None
    return ResourceTarget(
        user, ResourceContextDTO("user", user.id, scope, resolved=True)
    )


def scope_users(_db, principal, _action, grants, query):
    if admin_has_system_scope(grants):
        return query
    hospitals = {
        grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.HOSPITAL
        and grant.scope.scope_id is not None
    }
    if hospitals:
        return query.where(User.hospital_id.in_(hospitals))
    return query.where(false())


def user_facts(db, _principal, _action, target, facts):
    updates = {"domain_valid": bool(getattr(target.value, "is_active", False))}
    if (
        _principal.user_id is not None
        and target.value.id != _principal.user_id
        and {
            unit.id for unit in getattr(target.value, "lab_units", ())
        }
        & {
            unit.id
            for unit in getattr(db.get(User, _principal.user_id), "lab_units", ())
        }
    ):
        evidence = RelationshipEvidenceDTO(
            GrantSource.PEER,
            f"{_principal.user_id}:{target.value.id}",
            _principal.user_id,
            target.context.resource_type,
            target.context.resource_id,
            True,
            target.context.scope,
        )
        updates["relationships"] = (*facts.relationships, evidence)
    return replace(facts, **updates)


USER_ADAPTER = ResourceAdapter("user", resolve_user, scope_users, user_facts)


def resolve_user_creation_target(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, UserCreationTargetRef):
        return None
    if not is_positive_int(reference.hospital_id):
        return None
    hospital = db.get(Hospital, reference.hospital_id)
    if hospital is None:
        return None

    repository = GrantRepository(db)
    resolved_grants: list[tuple[Role, object]] = []
    for requested in reference.requested_grants:
        if not isinstance(requested, tuple) or len(requested) != 2:
            return None
        role, requested_scope = requested
        if (
            not isinstance(role, Role)
            or not isinstance(requested_scope, ScopeDTO)
            or not role_accepts_scope(
            role, requested_scope.scope_type
            )
        ):
            return None
        scope = repository.resolve_scope(requested_scope)
        if scope is None or scope.hospital_id != hospital.id:
            return None
        resolved_grants.append((role, scope))

    scope = repository.resolve_scope(
        ScopeDTO(ScopeType.HOSPITAL, hospital.id, hospital_id=hospital.id)
    )
    if scope is None:
        return None
    return ResourceTarget(
        tuple(resolved_grants),
        ResourceContextDTO(
            "user_creation_target",
            f"new:hospital:{hospital.id}",
            scope,
            state={"domain_valid": False},
            resolved=True,
        ),
    )


def user_creation_facts(_db, _principal, _action, target, facts):
    allowed = all(
        any(
            may_delegate(actor_grant.role, requested_role)
            and actor_grant.scope.contains(
                requested_scope, allow_system=actor_grant.role is Role.ADMIN
            )
            for actor_grant in facts.role_grants
        )
        for requested_role, requested_scope in target.value
    )
    return replace(facts, domain_valid=allowed)


USER_CREATION_TARGET_ADAPTER = ResourceAdapter(
    "user_creation_target",
    resolve_user_creation_target,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    user_creation_facts,
)
