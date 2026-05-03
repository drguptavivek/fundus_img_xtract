from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from authz.types import AuthzActor, GrantSource, RelationshipGrant


def actor_from_user(user: Any) -> AuthzActor:
    """Build a detached actor from the app's User-like object."""
    roles = frozenset(role.name for role in getattr(user, "roles", []) or [])
    return AuthzActor(
        id=int(getattr(user, "id")),
        roles=roles,
        hospital_id=getattr(user, "hospital_id", None),
    )


def admin_global_grant(actor: AuthzActor) -> RelationshipGrant | None:
    """Return admin-global grant when the actor has the admin role."""
    if "admin" not in {role.lower() for role in actor.roles}:
        return None
    return RelationshipGrant(source=GrantSource.ADMIN_GLOBAL)


def hospital_scope_grant(actor: AuthzActor) -> RelationshipGrant | None:
    """Return site-admin hospital scope for local admins with a hospital."""
    roles = {role.lower() for role in actor.roles}
    if "local_admin" not in roles or actor.hospital_id is None:
        return None
    return RelationshipGrant(source=GrantSource.HOSPITAL_SCOPE, hospital_id=actor.hospital_id)


def lab_unit_assignment_grants(user: Any) -> list[RelationshipGrant]:
    """Return explicit lab-unit relationship grants from a User-like object."""
    return [
        RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=int(lab_unit.id))
        for lab_unit in getattr(user, "lab_units", []) or []
    ]


def general_scope_grants(user: Any) -> list[RelationshipGrant]:
    """Return admin, hospital, and explicit lab-unit grants for general scoped actions."""
    actor = actor_from_user(user)
    grants: list[RelationshipGrant] = []
    for grant in (admin_global_grant(actor), hospital_scope_grant(actor)):
        if grant is not None:
            grants.append(grant)
    grants.extend(lab_unit_assignment_grants(user))
    return grants


def upload_profile_grant(profile: Any) -> RelationshipGrant:
    """Normalize an upload profile DTO/object to a ReBAC grant."""
    return RelationshipGrant(
        source=GrantSource.UPLOAD_PROFILE,
        lab_unit_id=getattr(profile, "lab_unit_id", None),
        attributes={
            "project_id": getattr(profile, "project_id"),
            "lab_unit_id": getattr(profile, "lab_unit_id"),
            "disease_ids": frozenset(getattr(profile, "disease_ids", frozenset())),
            "camera_ids": frozenset(getattr(profile, "camera_ids", frozenset())),
            "area_ids": frozenset(getattr(profile, "area_ids", frozenset())),
            "upload_kinds": frozenset(getattr(profile, "upload_kinds", frozenset())),
        },
    )


def upload_profile_grants(profiles: Iterable[Any]) -> list[RelationshipGrant]:
    return [upload_profile_grant(profile) for profile in profiles]


def grading_slot_grant(slot: Any) -> RelationshipGrant:
    """Normalize a UserDiseaseUnitRole-like object to a ReBAC grant."""
    return RelationshipGrant(
        source=GrantSource.GRADING_SLOT,
        lab_unit_id=getattr(slot, "lab_unit_id"),
        attributes={
            "disease_id": getattr(slot, "disease_id"),
            "can_grade_resident": bool(getattr(slot, "can_grade_resident", False)),
            "can_grade_resident2": bool(getattr(slot, "can_grade_resident2", False)),
            "can_arbitrate": bool(getattr(slot, "can_arbitrate", False)),
        },
    )


def grading_slot_grants(slots: Iterable[Any]) -> list[RelationshipGrant]:
    return [grading_slot_grant(slot) for slot in slots]
