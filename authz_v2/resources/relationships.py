"""Typed providers for contextual authorization relationships.

Providers append evidence derived from durable rows.  They never accept a
caller-supplied boolean as authority and cannot replace principal, resource, or
grant facts protected by the decision service.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from hmac import compare_digest

from sqlalchemy import select

from authz_v2.core.actions import Action
from authz_v2.core.principals import GrantSource, RelationshipEvidenceDTO
from authz_v2.core.roles import Role
from authz_v2.domain.models import (
    AuthorizationUploadProfileAssignment,
    ProjectLabUnitAuthorizationPolicy,
)
from authz_v2.resources.references import is_positive_int
from authz_v2.resources.registry import FactsProvider
from authz_v2.resources.upload_targets import ResolvedUploadTarget
from grading_allocation.exceptions import AllocationContextError
from grading_allocation.resolver import resolve_task_allocation_context
from models import (
    CuratedDataset,
    CuratedDatasetItem,
    DatasetShare,
    Grade,
    GradingTask,
    PasswordResetCredential,
    ProjectAutomatedRemoteInferenceRule,
    ProjectGraderAllocation,
    ProjectGradingAllocationPolicy,
    ProjectLabUnit,
    ProjectUploadProfileAssignment,
    UserDiseaseUnitRole,
)


def compose_facts(*providers: FactsProvider | None) -> FactsProvider:
    """Compose providers while preserving their evidence in declaration order."""
    active = tuple(provider for provider in providers if provider is not None)

    def composed(db, principal, action, target, facts):
        for provider in active:
            facts = provider(db, principal, action, target, facts)
        return facts

    return composed


def _append(facts, evidence: RelationshipEvidenceDTO, **updates):
    return replace(
        facts,
        relationships=(*facts.relationships, evidence),
        **updates,
    )


def ownership_facts(_db, principal, _action, target, facts):
    """Attest exact persisted ownership without trusting a caller claim."""
    if principal.user_id is None or target.context.owner_id != principal.user_id:
        return facts
    return _append(
        facts,
        RelationshipEvidenceDTO(
            GrantSource.OWNERSHIP,
            target.context.resource_id,
            principal.user_id,
            target.context.resource_type,
            target.context.resource_id,
            True,
            target.context.scope,
        ),
        owner_or_participant=True,
    )


def upload_profile_facts(db, principal, _action, target, facts):
    """Attest an exact active user/profile/site assignment."""
    scope = target.context.scope
    value = target.value
    if (
        principal.user_id is None
        or scope is None
        or scope.lab_unit_id is None
        or not isinstance(value, ResolvedUploadTarget)
    ):
        return facts
    if scope.project_id is not None and value.project_profile_id is not None:
        assignment = (
            db.execute(
                select(ProjectUploadProfileAssignment).where(
                    ProjectUploadProfileAssignment.user_id == principal.user_id,
                    ProjectUploadProfileAssignment.lab_unit_id == scope.lab_unit_id,
                    ProjectUploadProfileAssignment.project_upload_profile_id
                    == value.project_profile_id,
                    ProjectUploadProfileAssignment.active.is_(True),
                )
            )
            .scalars()
            .first()
        )
    elif scope.project_id is None:
        assignment = (
            db.execute(
                select(AuthorizationUploadProfileAssignment).where(
                    AuthorizationUploadProfileAssignment.user_id == principal.user_id,
                    AuthorizationUploadProfileAssignment.lab_unit_id
                    == scope.lab_unit_id,
                    AuthorizationUploadProfileAssignment.upload_profile_id
                    == value.profile.id,
                    AuthorizationUploadProfileAssignment.active.is_(True),
                )
            )
            .scalars()
            .first()
        )
    else:
        assignment = None
    if assignment is None:
        return facts
    evidence = RelationshipEvidenceDTO(
        GrantSource.UPLOAD_PROFILE,
        assignment.id,
        principal.user_id,
        target.context.resource_type,
        target.context.resource_id,
        True,
        scope,
        (("target_active", value.target_active),),
    )
    return _append(
        facts,
        evidence,
        upload_profile_matches=True,
        target_active=value.target_active,
    )


_GRADING_SLOT = {
    Action.GRADING_RESIDENT_SUBMIT: "resident",
    Action.GRADING_RESIDENT2_SUBMIT: "resident2",
    Action.GRADING_ARBITRATOR_SUBMIT: "arbitrator",
}
_ACCEPTED_STATE = {
    "resident": {"pending"},
    "resident2": {"resident_done"},
    "arbitrator": {"arbitration"},
}
_CLASSICAL_SLOT_FLAG = {
    "resident": UserDiseaseUnitRole.can_grade_resident,
    "resident2": UserDiseaseUnitRole.can_grade_resident2,
    "arbitrator": UserDiseaseUnitRole.can_arbitrate,
}


def grading_slot_facts(db, principal, action, target, facts):
    """Resolve workflow, conflicts, duplicates, and allocation for one slot."""
    slot = _GRADING_SLOT.get(action)
    task = target.value
    if slot is None or not isinstance(task, GradingTask) or principal.user_id is None:
        return facts
    existing = tuple(
        db.execute(select(Grade).where(Grade.task_id == task.id)).scalars()
    )
    user_grades = tuple(
        grade for grade in existing if grade.grader_user_id == principal.user_id
    )
    workflow_accepts = task.state in _ACCEPTED_STATE[slot]
    no_duplicate = all(grade.role_slot != slot for grade in user_grades)
    conflicts = {
        "resident": {"resident2"},
        "resident2": {"resident"},
        "arbitrator": {"resident", "resident2"},
    }
    no_conflict = all(grade.role_slot not in conflicts[slot] for grade in user_grades)

    slot_assignment = (
        db.execute(
            select(UserDiseaseUnitRole).where(
                UserDiseaseUnitRole.user_id == principal.user_id,
                UserDiseaseUnitRole.disease_id == task.disease_id,
                UserDiseaseUnitRole.lab_unit_id == task.lab_unit_id,
                UserDiseaseUnitRole.active.is_(True),
                _CLASSICAL_SLOT_FLAG[slot].is_(True),
            )
        )
        .scalars()
        .first()
    )
    slot_matches = slot_assignment is not None

    enforcement = False
    allocation_matches = True
    allocation_id = None
    if task.project_id is not None:
        policy = db.execute(
            select(ProjectGradingAllocationPolicy).where(
                ProjectGradingAllocationPolicy.project_id == task.project_id
            )
        ).scalar_one_or_none()
        enforcement = bool(policy and policy.enforcement_enabled)
        if enforcement:
            capacity = "arbitrator" if slot == "arbitrator" else "resident"
            try:
                allocation_context = resolve_task_allocation_context(db, task)
            except AllocationContextError:
                allocation_context = None
            target = allocation_context.target if allocation_context else None
            allocation = None
            if (
                allocation_context is not None
                and allocation_context.project_id == task.project_id
                and target is not None
            ):
                allocation = (
                    db.execute(
                        select(ProjectGraderAllocation).where(
                            ProjectGraderAllocation.project_id == task.project_id,
                            ProjectGraderAllocation.lab_unit_id == task.lab_unit_id,
                            ProjectGraderAllocation.user_id == principal.user_id,
                            ProjectGraderAllocation.capacity == capacity,
                            ProjectGraderAllocation.scope == target.scope.value,
                            ProjectGraderAllocation.disease_id.is_not_distinct_from(
                                target.disease_id
                            ),
                            ProjectGraderAllocation.encounter_set_type_id.is_not_distinct_from(
                                target.encounter_set_type_id
                            ),
                            ProjectGraderAllocation.active.is_(True),
                        )
                    )
                    .scalars()
                    .first()
                )
            allocation_matches = allocation is not None
            allocation_id = allocation.id if allocation else None

    slot_evidence = RelationshipEvidenceDTO(
        GrantSource.GRADING_SLOT,
        f"{task.id}:{slot}",
        principal.user_id,
        target.context.resource_type,
        target.context.resource_id,
        slot_matches,
        target.context.scope,
        (
            ("workflow_accepts", workflow_accepts),
            ("no_conflict", no_conflict),
            ("no_duplicate", no_duplicate),
            ("allocation_enforced", enforcement),
        ),
    )
    facts = _append(
        facts,
        slot_evidence,
        grading_slot_matches=slot_matches,
        allocation_enforced=enforcement,
        workflow_accepts=workflow_accepts,
        no_conflict=no_conflict,
        no_duplicate=no_duplicate,
    )
    if enforcement and allocation_matches:
        facts = _append(
            facts,
            RelationshipEvidenceDTO(
                GrantSource.PROJECT_ALLOCATION,
                allocation_id,
                principal.user_id,
                target.context.resource_type,
                target.context.resource_id,
                True,
                target.context.scope,
            ),
            allocation_matches=True,
        )
    return facts


def participation_facts(db, principal, _action, target, facts):
    """Attest authorship of any grade on the exact grading task."""
    task = target.value
    if not isinstance(task, GradingTask) or principal.user_id is None:
        return facts
    grade_id = (
        db.execute(
            select(Grade.id)
            .where(
                Grade.task_id == task.id,
                Grade.grader_user_id == principal.user_id,
            )
            .order_by(Grade.id)
        )
        .scalars()
        .first()
    )
    if grade_id is None:
        return facts
    return _append(
        facts,
        RelationshipEvidenceDTO(
            GrantSource.PARTICIPATION,
            grade_id,
            principal.user_id,
            target.context.resource_type,
            target.context.resource_id,
            True,
            target.context.scope,
        ),
        owner_or_participant=True,
    )


def signed_credential_facts(db, _principal, _action, target, facts):
    """Attest exact active credential selected by the signed session."""
    session = facts.session
    if (
        session is None
        or session.channel.value != "signed"
        or session.credential_id != str(target.context.resource_id)
        or not session.credential_proof
    ):
        return facts
    value = target.value
    now = datetime.now(UTC)
    supplied_hash = sha256(session.credential_proof.encode("utf-8")).hexdigest()
    proof_valid = compare_digest(supplied_hash, value.token_hash)
    if isinstance(value, PasswordResetCredential):
        valid = value.consumed_at is None and value.expires_at > now
    elif isinstance(value, DatasetShare):
        valid = bool(value.is_active and value.expires_at > now)
    else:
        valid = False
    if not valid or not proof_valid:
        return facts
    return _append(
        facts,
        RelationshipEvidenceDTO(
            GrantSource.SIGNED_CREDENTIAL,
            value.id,
            None,
            target.context.resource_type,
            target.context.resource_id,
            True,
            None,
        ),
        credential_valid=True,
    )


def automation_rule_facts(db, _principal, action, target, facts):
    """Attest a stored active project automation rule for the exact target."""
    session = facts.session
    scope = target.context.scope
    if (
        session is None
        or scope is None
        or scope.project_id is None
        or session.channel.value != "automation"
        or session.automation_rule_id is None
    ):
        return facts
    rule_id = target.context.state.get("automation_rule_id")
    if not is_positive_int(rule_id) or session.automation_rule_id != rule_id:
        return facts
    rule = db.get(ProjectAutomatedRemoteInferenceRule, rule_id)
    if rule is not None and (not rule.active or rule.project_id != scope.project_id):
        rule = None
    if rule is None:
        return facts
    return _append(
        facts,
        RelationshipEvidenceDTO(
            GrantSource.AUTOMATION_RULE,
            rule.id,
            None,
            target.context.resource_type,
            target.context.resource_id,
            True,
            scope,
            (("target_matches", True),),
        ),
        automation_rule_matches=True,
        automation_target_matches=True,
    )


def site_policy_facts(db, _principal, action, target, facts):
    """Apply default-closed project-site release and curation switches."""
    scope = target.context.scope
    controlled = {
        Action.DATASET_CURATION_UPDATE: "dataset_creation_enabled",
        Action.DATASET_FINALIZE: "dataset_creation_enabled",
        Action.DATASET_DELETE: "dataset_creation_enabled",
        Action.DATASET_SHARE_MANAGE: "dataset_sharing_enabled",
        Action.DATASET_EXPORT_GRADES: "grade_export_enabled",
    }
    flag = controlled.get(action)
    if flag is None or scope is None or scope.project_id is None:
        return facts
    if scope.project_lab_unit_id is not None:
        policies = tuple(
            db.execute(
                select(ProjectLabUnitAuthorizationPolicy).where(
                    ProjectLabUnitAuthorizationPolicy.project_lab_unit_id
                    == scope.project_lab_unit_id
                )
            ).scalars()
        )
    else:
        value = target.value
        dataset = value[0] if isinstance(value, tuple) else None
        if not isinstance(dataset, CuratedDataset):
            return replace(facts, domain_valid=False)
        site_ids = tuple(
            db.execute(
                select(ProjectLabUnit.id)
                .join(
                    GradingTask,
                    (GradingTask.project_id == ProjectLabUnit.project_id)
                    & (GradingTask.lab_unit_id == ProjectLabUnit.lab_unit_id),
                )
                .join(CuratedDatasetItem, CuratedDatasetItem.task_id == GradingTask.id)
                .where(CuratedDatasetItem.dataset_id == dataset.id)
                .distinct()
            ).scalars()
        )
        policies = tuple(
            db.execute(
                select(ProjectLabUnitAuthorizationPolicy).where(
                    ProjectLabUnitAuthorizationPolicy.project_lab_unit_id.in_(site_ids)
                )
            ).scalars()
        )
        if not site_ids or len(policies) != len(site_ids):
            return replace(facts, domain_valid=False)
    allowed = bool(policies) and all(bool(getattr(policy, flag)) for policy in policies)
    return replace(facts, domain_valid=facts.domain_valid and allowed)


def dataset_state_facts(_db, _principal, action, target, facts):
    """Resolve dataset lifecycle from the dataset row, never its scope binding."""
    value = target.value
    dataset = value[0] if isinstance(value, tuple) else None
    if not isinstance(dataset, CuratedDataset):
        return replace(facts, domain_valid=False)
    if action in {
        Action.DATASET_EXPORT_CREATE,
        Action.DATASET_EXPORT_DOWNLOAD,
        Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS,
        Action.DATASET_EXPORT_GRADES,
        Action.DATASET_SHARE_MANAGE,
    }:
        valid = dataset.is_active and dataset.is_finalized
    elif action in {
        Action.DATASET_CURATION_UPDATE,
        Action.DATASET_FINALIZE,
        Action.DATASET_DELETE,
    }:
        valid = dataset.is_active and not dataset.is_finalized
    else:
        valid = dataset.is_active
    return replace(facts, domain_valid=facts.domain_valid and bool(valid))


def pii_image_facts(_db, _principal, action, target, facts):
    """Withhold identifier-flagged images from masked image delivery."""
    if action is not Action.MEDIA_IMAGE_VIEW:
        return facts
    if not bool(getattr(target.value, "is_pii", False)):
        return facts
    identifier_reader = bool(
        facts.active_roles & {Role.ADMIN, Role.VERIFIER, Role.DATASET_CREATOR}
    )
    return replace(facts, domain_valid=facts.domain_valid and identifier_reader)
