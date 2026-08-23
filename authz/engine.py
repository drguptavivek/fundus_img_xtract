"""Pure policy evaluator for actor, action, resource, and relationship grants."""

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

    if policy.public:
        return AuthzDecision.allow(action, GrantSource.PUBLIC)

    resource = resource or ResourceRef(type="none")
    actor_role_matches = actor.has_any_role(policy.roles)
    for grant in grants:
        if grant.source not in policy.grant_sources:
            continue
        if grant.source in _PROJECT_SOURCES and not policy.accepts_project_scope(
            hospital_id=grant.attr("hospital_id"), lab_unit_id=grant.attr("lab_unit_id")
        ):
            # The grant is narrower than the breadth of this action's effect.
            continue
        if _grant_matches(actor, resource, action, grant, policy) and _grant_supplies_authority(
            actor_role_matches, policy.roles, policy.roles_for_project(), policy.capabilities, grant
        ):
            return AuthzDecision.allow(action, grant.source)

    return AuthzDecision.deny(
        action,
        "missing_relationship" if actor_role_matches else "missing_role",
    )


_PROJECT_SOURCES = frozenset({
    GrantSource.PROJECT_ROLE,
    GrantSource.LEGACY_PROJECT_CAPABILITY,
    GrantSource.PROJECT_COLLABORATOR,
})


def _grant_supplies_authority(
    actor_role_matches: bool,
    policy_roles: frozenset[str],
    policy_project_roles: frozenset[str],
    policy_capabilities: frozenset[str],
    grant: RelationshipGrant,
) -> bool:
    if grant.source in {
        GrantSource.ADMIN_GLOBAL,
        GrantSource.HOSPITAL_SCOPE,
        GrantSource.OWN_HOSPITAL,
        GrantSource.LAB_UNIT_ASSIGNMENT,
        GrantSource.UPLOAD_PROFILE,
        GrantSource.GRADING_SLOT,
    }:
        return actor_role_matches
    if grant.source == GrantSource.PROJECT_ROLE:
        return bool(
            {str(role).lower() for role in grant.attr("role_names") or ()}
            & {role.lower() for role in policy_project_roles}
        )
    if grant.source == GrantSource.LEGACY_PROJECT_CAPABILITY:
        return bool(set(grant.attr("capabilities") or ()) & set(policy_capabilities))
    if grant.source == GrantSource.PROJECT_COLLABORATOR:
        return "collaborator" in {role.lower() for role in policy_project_roles}
    if grant.source == GrantSource.MEDIA_UPLOADER:
        return actor_role_matches
    if grant.source in {
        GrantSource.TASK_ELIGIBILITY,
        GrantSource.SIGNED_MEDIA_TOKEN,
        GrantSource.SELF,
    }:
        return True
    return False


def _grant_matches(
    actor: AuthzActor,
    resource: ResourceRef,
    action: str,
    grant: RelationshipGrant,
    policy,
) -> bool:
    if grant.source == GrantSource.ADMIN_GLOBAL:
        return "admin" in {role.lower() for role in actor.roles}

    # Classical scope is the non-project rule. A resource that belongs to a
    # project is reachable only through an explicit project relationship;
    # hospital membership or a lab-unit assignment never reaches it.
    if grant.source == GrantSource.OWN_HOSPITAL:
        return (
            _reachable_classically(policy, resource)
            and grant.hospital_id is not None
            and resource.attr("hospital_id") == grant.hospital_id
        )

    if grant.source == GrantSource.HOSPITAL_SCOPE:
        return _reachable_classically(policy, resource) and _matches_hospital_scope(actor, resource, grant)

    if grant.source == GrantSource.LAB_UNIT_ASSIGNMENT:
        return _reachable_classically(policy, resource) and _matches_lab_unit(resource, grant)

    if grant.source == GrantSource.UPLOAD_PROFILE:
        return _matches_upload_profile(resource, grant)

    if grant.source == GrantSource.GRADING_SLOT:
        return _matches_grading_slot(resource, action, grant)

    if grant.source in {
        GrantSource.PROJECT_ROLE,
        GrantSource.LEGACY_PROJECT_CAPABILITY,
        GrantSource.PROJECT_COLLABORATOR,
    }:
        return _matches_project_scope(resource, grant)

    if grant.source == GrantSource.TASK_ELIGIBILITY:
        return grant.resource_id == resource.id or grant.attr("media_uuid") == resource.id

    if grant.source == GrantSource.MEDIA_UPLOADER:
        return grant.resource_id == resource.id

    if grant.source == GrantSource.SIGNED_MEDIA_TOKEN:
        return grant.resource_id == resource.id

    if grant.source == GrantSource.SELF:
        # Actions that name no resource are implicitly about the actor's own
        # record; actions that name one must name the actor's own record.
        if resource.id is None:
            return True
        return str(resource.id) == str(grant.resource_id)

    return False


def _matches_project_scope(resource: ResourceRef, grant: RelationshipGrant) -> bool:
    if resource.attr("project_id") is None:
        return False
    if grant.attr("project_id") != resource.attr("project_id"):
        return False
    grant_hospital_id = grant.attr("hospital_id")
    grant_lab_unit_id = grant.attr("lab_unit_id")
    if grant_lab_unit_id is not None:
        return grant_lab_unit_id == resource.attr("lab_unit_id")
    if grant_hospital_id is not None:
        return grant_hospital_id == resource.attr("hospital_id")
    return True


def _reachable_classically(policy, resource: ResourceRef) -> bool:
    """Whether hospital or lab scope may reach this resource.

    Normally only rows outside every project. An action that is not
    project-gated - aggregate operational reporting - reaches all rows.
    """
    return not policy.project_gated or resource.attr("project_id") is None


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
