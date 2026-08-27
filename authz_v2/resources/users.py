"""Authoritative user-resource resolver and SQL scoper."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import false

from authz_v2.core.resources import ResourceContextDTO
from authz_v2.core.roles import ScopeType
from authz_v2.resources.references import is_positive_int
from authz_v2.resources.registry import ResourceAdapter, ResourceTarget
from authz_v2.resources.scoping import admin_has_system_scope, resolve_scope
from models import User


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


def user_facts(_db, _principal, _action, target, facts):
    return replace(facts, domain_valid=bool(getattr(target.value, "is_active", False)))


USER_ADAPTER = ResourceAdapter("user", resolve_user, scope_users, user_facts)
