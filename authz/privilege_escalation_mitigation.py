"""Fail-closed safeguards for authorization grant mutations.

This module contains only cross-cutting privilege-escalation controls.  It does
not decide upload, grading, clinical, or project workflow eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from authz.project_roles import (
    PI_DELEGATORS,
    PROJECT_ADMIN,
    PROJECT_ADMIN_STANDARD_DELEGABLE_ROLES,
    PROJECT_ASSIGNABLE_ROLES,
    PROJECT_PI,
    PII_EXPORTER,
    SITE_PI,
)

PROJECT_SCOPE = "project"
LAB_UNIT_SCOPE = "lab_unit"


@dataclass(frozen=True)
class DelegatorGrant:
    """One current manager role and its exact containing scope."""

    role_name: str
    scope_type: str
    lab_unit_id: int | None


def delegable_project_roles(
    *,
    actor_user_id: int | None,
    target_user_id: int | None,
    actor_is_admin: bool,
    requested_scope_type: str | None,
    requested_lab_unit_id: int | None,
    delegator_grants: Iterable[DelegatorGrant],
) -> frozenset[str]:
    """Return the roles the actor may grant; incomplete facts return none.

    System Admin may grant every supported project role.  Project/Site PI may
    grant Project Admin, and Project Admin may grant operational roles, only
    inside a scope already held by that delegator.  Non-admin self-grants are
    never allowed.
    """
    if not _complete_request_scope(requested_scope_type, requested_lab_unit_id):
        return frozenset()
    if not actor_user_id or not target_user_id:
        return frozenset()
    if actor_is_admin:
        return PROJECT_ASSIGNABLE_ROLES
    if actor_user_id == target_user_id:
        return frozenset()

    contained_roles = {
        grant.role_name
        for grant in delegator_grants
        if _grant_contains(
            grant,
            requested_scope_type=requested_scope_type,
            requested_lab_unit_id=requested_lab_unit_id,
        )
    }
    result: set[str] = set()
    if contained_roles & PI_DELEGATORS:
        result.add(PROJECT_ADMIN)
    if PROJECT_ADMIN in contained_roles:
        result.update(PROJECT_ADMIN_STANDARD_DELEGABLE_ROLES)
    if any(
        grant.role_name == PROJECT_ADMIN
        and grant.scope_type == PROJECT_SCOPE
        and grant.lab_unit_id is None
        for grant in delegator_grants
    ):
        result.add(PII_EXPORTER)
    return frozenset(result)


def can_delegate_project_role(*, target_role: str | None, **facts) -> bool:
    """Check one requested target role against the actor's delegation ceiling."""
    if not target_role or target_role in {PROJECT_PI, SITE_PI} and not facts.get("actor_is_admin"):
        return False
    return target_role in delegable_project_roles(**facts)


def _complete_request_scope(scope_type: str | None, lab_unit_id: int | None) -> bool:
    if scope_type == PROJECT_SCOPE:
        return lab_unit_id is None
    if scope_type == LAB_UNIT_SCOPE:
        return bool(lab_unit_id and lab_unit_id > 0)
    return False


def _grant_contains(
    grant: DelegatorGrant,
    *,
    requested_scope_type: str,
    requested_lab_unit_id: int | None,
) -> bool:
    if grant.scope_type == PROJECT_SCOPE and grant.lab_unit_id is None:
        return True
    return (
        requested_scope_type == LAB_UNIT_SCOPE
        and grant.scope_type == LAB_UNIT_SCOPE
        and grant.lab_unit_id is not None
        and grant.lab_unit_id == requested_lab_unit_id
    )
