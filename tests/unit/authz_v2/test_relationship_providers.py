from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

from authz_v2.core.actions import Action
from authz_v2.core.principals import (
    EvaluationFactsDTO,
    GrantSource,
    PrincipalDTO,
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.models import PasswordResetCredential
from authz_v2.resources.registry import ResourceTarget
from authz_v2.resources.relationships import (
    automation_rule_facts,
    dataset_state_facts,
    grading_slot_facts,
    participation_facts,
    pii_image_facts,
    signed_credential_facts,
    site_policy_facts,
    upload_profile_facts,
)
from authz_v2.resources.upload_targets import ResolvedUploadTarget
from models import (
    CuratedDataset,
    GradingTask,
    ProjectAutomatedRemoteInferenceRule,
    ProjectGradingAllocationPolicy,
    ProjectLabUnitAuthorizationPolicy,
    ProjectUploadProfileAssignment,
    UploadProfile,
)


class Result:
    def __init__(self, values=()):
        self.values = tuple(values)

    def scalars(self):
        return self

    def first(self):
        return self.values[0] if self.values else None

    def scalar_one_or_none(self):
        if len(self.values) > 1:
            raise AssertionError("test result is not singular")
        return self.first()

    def __iter__(self):
        return iter(self.values)


class QueueDB:
    def __init__(self, *results):
        self.results = list(results)

    def execute(self, _statement):
        return self.results.pop(0)


PROJECT_SITE = ScopeDTO(
    ScopeType.PROJECT_LAB_UNIT,
    30,
    hospital_id=10,
    lab_unit_id=20,
    project_id=40,
    project_lab_unit_id=30,
)


def _facts(resource_type: str, resource_id: int = 7, *, signed=False):
    channel = SessionChannel.SIGNED if signed else SessionChannel.WEB
    session = SessionContextDTO(
        "request-1",
        channel,
        datetime.now(UTC),
        credential_id=str(resource_id) if signed else None,
    )
    principal = PrincipalDTO(1, True, True, session)
    context = ResourceContextDTO(resource_type, resource_id, PROJECT_SITE)
    return principal, EvaluationFactsDTO(principal, session=session, resource=context)


def test_upload_provider_requires_an_exact_active_assignment():
    principal, facts = _facts("project_upload_target")
    assignment = ProjectUploadProfileAssignment(id=51, user_id=1, lab_unit_id=20)
    profile = UploadProfile(id=9, active=True)
    target = ResourceTarget(
        ResolvedUploadTarget(object(), profile, 71, True), facts.resource
    )
    provided = upload_profile_facts(
        QueueDB(Result((assignment,))),
        principal,
        Action.PROJECT_UPLOAD_CREATE,
        target,
        facts,
    )
    assert provided.relationships[0].relationship is GrantSource.UPLOAD_PROFILE
    assert provided.relationships[0].attribute("target_active") is True

    denied = upload_profile_facts(
        QueueDB(Result()), principal, Action.PROJECT_UPLOAD_CREATE, target, facts
    )
    assert not denied.relationships


def test_grading_provider_attests_workflow_and_default_off_allocation():
    principal, facts = _facts("grading_task")
    task = GradingTask(id=7, project_id=40, lab_unit_id=20, state="pending")
    policy = ProjectGradingAllocationPolicy(project_id=40, enforcement_enabled=False)
    provided = grading_slot_facts(
        QueueDB(Result(), Result((policy,))),
        principal,
        Action.GRADING_RESIDENT_SUBMIT,
        ResourceTarget(task, facts.resource),
        facts,
    )
    evidence = provided.relationships[0]
    assert evidence.relationship is GrantSource.GRADING_SLOT
    assert evidence.attribute("workflow_accepts") is True
    assert evidence.attribute("allocation_enforced") is False
    assert provided.no_conflict and provided.no_duplicate


def test_signed_credential_requires_exact_session_binding_and_expiry():
    principal, facts = _facts("password_reset_credential", signed=True)
    raw_token = "correct-reset-token"
    session = replace(principal.session, credential_proof=raw_token)
    principal = replace(principal, session=session)
    facts = replace(facts, principal=principal, session=session)
    credential = PasswordResetCredential(
        id=7,
        user_id=1,
        token_hash=sha256(raw_token.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    target = ResourceTarget(credential, facts.resource)
    allowed = signed_credential_facts(
        None, principal, Action.AUTH_PASSWORD_RESET_COMPLETE, target, facts
    )
    assert allowed.credential_valid
    assert allowed.relationships[0].relationship is GrantSource.SIGNED_CREDENTIAL

    wrong_session = SessionContextDTO(
        "request-2", SessionChannel.SIGNED, datetime.now(UTC), credential_id="8"
    )
    denied = signed_credential_facts(
        None,
        principal,
        Action.AUTH_PASSWORD_RESET_COMPLETE,
        target,
        EvaluationFactsDTO(principal, session=wrong_session, resource=facts.resource),
    )
    assert not denied.relationships


def test_participation_is_derived_from_exact_grade_authorship():
    principal, facts = _facts("grading_task")
    task = GradingTask(id=7, project_id=40, lab_unit_id=20, state="final")
    target = ResourceTarget(task, facts.resource)
    allowed = participation_facts(
        QueueDB(Result((91,))), principal, Action.GRADING_GRADES_VIEW, target, facts
    )
    assert allowed.owner_or_participant
    assert allowed.relationships[0].relationship is GrantSource.PARTICIPATION
    denied = participation_facts(
        QueueDB(Result()), principal, Action.GRADING_GRADES_VIEW, target, facts
    )
    assert not denied.relationships


def test_site_policy_is_default_closed_and_action_specific():
    principal, facts = _facts("dataset")
    facts = replace(facts, domain_valid=True)
    target = ResourceTarget(object(), facts.resource)
    enabled = ProjectLabUnitAuthorizationPolicy(
        project_lab_unit_id=30,
        grade_export_enabled=True,
        dataset_creation_enabled=False,
        dataset_sharing_enabled=False,
    )
    assert site_policy_facts(
        QueueDB(Result((enabled,))),
        principal,
        Action.DATASET_EXPORT_GRADES,
        target,
        facts,
    ).domain_valid
    assert not site_policy_facts(
        QueueDB(Result()),
        principal,
        Action.DATASET_EXPORT_GRADES,
        target,
        facts,
    ).domain_valid


def test_dataset_lifecycle_is_loaded_independently_of_scope_binding():
    principal, facts = _facts("dataset")
    facts = replace(facts, domain_valid=True)
    finalized = CuratedDataset(id=7, is_active=True, is_finalized=True)
    target = ResourceTarget((finalized, object()), facts.resource)
    assert dataset_state_facts(
        None, principal, Action.DATASET_EXPORT_CREATE, target, facts
    ).domain_valid


def test_image_disclosure_provider_never_overrides_an_invalid_target_state():
    principal, facts = _facts("image")
    target = ResourceTarget(SimpleNamespace(is_pii=False), facts.resource)
    assert not pii_image_facts(
        None, principal, Action.MEDIA_IMAGE_VIEW, target, facts
    ).domain_valid

    pii_target = ResourceTarget(SimpleNamespace(is_pii=True), facts.resource)
    verifier = replace(
        facts, domain_valid=True, active_roles=frozenset({Role.VERIFIER})
    )
    assert pii_image_facts(
        None, principal, Action.MEDIA_IMAGE_VIEW, pii_target, verifier
    ).domain_valid
    assert not pii_image_facts(
        None,
        principal,
        Action.MEDIA_IMAGE_VIEW,
        pii_target,
        replace(verifier, active_roles=frozenset()),
    ).domain_valid
    assert not dataset_state_facts(
        None, principal, Action.DATASET_CURATION_UPDATE, target, facts
    ).domain_valid


def test_automation_requires_exact_bound_rule_for_non_project_target():
    session = SessionContextDTO(
        "worker-1",
        SessionChannel.AUTOMATION,
        datetime.now(UTC),
        automation_rule_id=81,
    )
    principal = PrincipalDTO(None, True, False, session)
    context = ResourceContextDTO(
        "inference_target",
        7,
        PROJECT_SITE,
        state={"automation_rule_id": 81},
    )
    facts = EvaluationFactsDTO(principal, session=session, resource=context)
    rule = ProjectAutomatedRemoteInferenceRule(id=81, project_id=40, active=True)

    class RuleDB:
        def __init__(self, value):
            self.value = value

        def get(self, _model, _resource_id):
            return self.value

    target = ResourceTarget(object(), context)
    allowed = automation_rule_facts(
        RuleDB(rule), principal, Action.INFERENCE_WAI_RUN, target, facts
    )
    assert allowed.automation_target_matches
    assert allowed.relationships[0].relationship is GrantSource.AUTOMATION_RULE
    wrong_project = ProjectAutomatedRemoteInferenceRule(
        id=81, project_id=41, active=True
    )
    denied = automation_rule_facts(
        RuleDB(wrong_project), principal, Action.INFERENCE_WAI_RUN, target, facts
    )
    assert not denied.relationships


def test_project_automation_requires_the_calling_worker_to_supply_exact_rule_id():
    session = SessionContextDTO(
        "worker-1",
        SessionChannel.AUTOMATION,
        datetime.now(UTC),
        automation_rule_id=81,
    )
    principal = PrincipalDTO(None, True, False, session)
    project_scope = ScopeDTO(ScopeType.PROJECT, 40, project_id=40)
    missing_context = ResourceContextDTO("project", 40, project_scope)
    missing = EvaluationFactsDTO(
        principal, session=session, resource=missing_context, domain_valid=True
    )
    rule = ProjectAutomatedRemoteInferenceRule(id=81, project_id=40, active=True)

    class RuleDB:
        def get(self, _model, _resource_id):
            return rule

    assert not automation_rule_facts(
        RuleDB(),
        principal,
        Action.PROJECT_WAI_RUN,
        ResourceTarget(object(), missing_context),
        missing,
    ).relationships

    exact_context = replace(missing_context, state={"automation_rule_id": rule.id})
    allowed = automation_rule_facts(
        RuleDB(),
        principal,
        Action.PROJECT_WAI_RUN,
        ResourceTarget(object(), exact_context),
        replace(missing, resource=exact_context),
    )
    assert allowed.automation_rule_matches
