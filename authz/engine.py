from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from authz.policies import get_policy
from authz.types import AuthzActor, AuthzDecision, GrantSource, RelationshipGrant, ResourceRef


def authorize(
    actor: AuthzActor,
    action: str,
    resource: ResourceRef | None = None,
    *,
    grants: Iterable[RelationshipGrant] = (),
) -> AuthzDecision:
    """Authorize one actor/action/resource tuple against resolved ReBAC grants."""
    policy = get_policy(action)
    if policy is None:
        return AuthzDecision.deny(action, "unknown_action")

    if not actor.has_any_role(policy.roles):
        return AuthzDecision.deny(action, "missing_role")

    resource = resource or ResourceRef(type="none")
    for grant in grants:
        if grant.source not in policy.grant_sources:
            continue
        if _grant_matches(actor, resource, action, grant):
            return AuthzDecision.allow(action, grant.source)

    return AuthzDecision.deny(action, "missing_relationship")


def _grant_matches(
    actor: AuthzActor,
    resource: ResourceRef,
    action: str,
    grant: RelationshipGrant,
) -> bool:
    if grant.source == GrantSource.ADMIN_GLOBAL:
        return "admin" in {role.lower() for role in actor.roles}

    if grant.source == GrantSource.HOSPITAL_SCOPE:
        return _matches_hospital_scope(actor, resource, grant)

    if grant.source == GrantSource.LAB_UNIT_ASSIGNMENT:
        return _matches_lab_unit(resource, grant)

    if grant.source == GrantSource.UPLOAD_PROFILE:
        return _matches_upload_profile(resource, grant)

    if grant.source == GrantSource.GRADING_SLOT:
        return _matches_grading_slot(resource, action, grant)

    return False


def _matches_hospital_scope(actor: AuthzActor, resource: ResourceRef, grant: RelationshipGrant) -> bool:
    resource_hospital_id = resource.attr("hospital_id")
    grant_hospital_id = grant.hospital_id
    if grant_hospital_id is None or actor.hospital_id != grant_hospital_id:
        return False
    if resource_hospital_id is not None:
        return resource_hospital_id == grant_hospital_id
    return True


def _matches_lab_unit(resource: ResourceRef, grant: RelationshipGrant) -> bool:
    resource_lab_unit_id = resource.attr("lab_unit_id")
    return grant.lab_unit_id is not None and resource_lab_unit_id == grant.lab_unit_id


def _matches_upload_profile(resource: ResourceRef, grant: RelationshipGrant) -> bool:
    return (
        resource.attr("project_id") == grant.attr("project_id")
        and resource.attr("lab_unit_id") == grant.attr("lab_unit_id")
        and _contains(grant.attr("disease_ids"), resource.attr("disease_id"))
        and _contains(grant.attr("camera_ids"), resource.attr("camera_id"))
        and _contains(grant.attr("area_ids"), resource.attr("area_id"))
        and _contains(grant.attr("upload_kinds"), resource.attr("upload_kind"))
    )


def _matches_grading_slot(resource: ResourceRef, action: str, grant: RelationshipGrant) -> bool:
    slot_flag_by_action = {
        "grading.resident.submit": "can_grade_resident",
        "grading.resident2.submit": "can_grade_resident2",
        "grading.arbitrator.submit": "can_arbitrate",
    }
    slot_flag = slot_flag_by_action.get(action)
    return (
        slot_flag is not None
        and grant.lab_unit_id == resource.attr("lab_unit_id")
        and grant.attr("disease_id") == resource.attr("disease_id")
        and bool(grant.attr(slot_flag))
    )


def _contains(values: Any, value: Any) -> bool:
    if values is None:
        return False
    return value in values
