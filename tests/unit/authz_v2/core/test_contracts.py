from __future__ import annotations

import ast
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from authz_v2.core.actions import ACTION_MANIFEST, ACTION_MIGRATION_MAP, Action
from authz_v2.core.catalogue import CATALOGUE, check_action
from authz_v2.core.expressions import (
    ActivePrincipalRequirement,
    AnyRoleRequirement,
    BooleanRequirement,
    Expression,
    GrantSourceRequirement,
    IdentifierReleaseRequirement,
    PublicRequirement,
    RelationshipRequirement,
    ScopedRoleRequirement,
    ScopeRequirement,
    SessionChannelRequirement,
    all_of,
    any_of,
    evaluate,
)
from authz_v2.core.principals import (
    EvaluationFactsDTO,
    GrantSource,
    PrincipalDTO,
    RelationshipEvidenceDTO,
    RoleGrantDTO,
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import (
    DisclosureClass,
    ResourceContextDTO,
    ScopeDTO,
    ScopeSetDTO,
)
from authz_v2.core.roles import (
    ROLE_CONTRACTS,
    Role,
    ScopeType,
    may_delegate,
    role_accepts_scope,
)


def _base_facts(resource_type: str | None) -> EvaluationFactsDTO:
    lab = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)
    resource = None
    if resource_type is not None:
        resource = ResourceContextDTO(resource_type, 100, lab, resolved=True)
    return EvaluationFactsDTO(
        principal=PrincipalDTO(1, active=True, authenticated=True),
        resource=resource,
        reachable_scopes=ScopeSetDTO(frozenset({lab})),
        exact_resource=True,
    )


def _satisfy(requirement, facts: EvaluationFactsDTO) -> EvaluationFactsDTO:
    if isinstance(requirement, Expression):
        children = (
            requirement.requirements[:1]
            if requirement.operator == "any_of"
            else requirement.requirements
        )
        for child in children:
            facts = _satisfy(child, facts)
        return facts
    if isinstance(requirement, ActivePrincipalRequirement):
        return replace(
            facts, principal=PrincipalDTO(1, active=True, authenticated=True)
        )
    if isinstance(requirement, PublicRequirement):
        return facts
    if isinstance(requirement, AnyRoleRequirement):
        role = next(iter(requirement.roles))
        scope = (
            ScopeDTO(ScopeType.SYSTEM)
            if role is Role.ADMIN
            else ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)
        )
        grant = RoleGrantDTO(len(facts.role_grants) + 1, role, scope)
        return replace(
            facts,
            active_roles=facts.active_roles | {role},
            role_grants=(*facts.role_grants, grant),
            grant_ids=(*facts.grant_ids, grant.grant_id),
        )
    if isinstance(requirement, ScopedRoleRequirement):
        assert facts.resource is not None
        assert facts.resource.scope is not None
        role = next(iter(requirement.roles))
        scope = (
            ScopeDTO(ScopeType.SYSTEM)
            if requirement.allow_system and role is Role.ADMIN
            else facts.resource.scope
        )
        grant = RoleGrantDTO(len(facts.role_grants) + 1, role, scope)
        return replace(
            facts,
            active_roles=facts.active_roles | {role},
            role_grants=(*facts.role_grants, grant),
            grant_ids=(*facts.grant_ids, grant.grant_id),
        )
    if isinstance(requirement, GrantSourceRequirement):
        source = next(iter(requirement.sources))
        if source is GrantSource.AUTHORIZATION_GRANT:
            return facts
        assert facts.resource is not None
        evidence = RelationshipEvidenceDTO(
            source,
            len(facts.relationships) + 1,
            facts.principal.user_id,
            facts.resource.resource_type,
            facts.resource.resource_id,
            True,
            facts.resource.scope,
        )
        return replace(facts, relationships=(*facts.relationships, evidence))
    if isinstance(requirement, RelationshipRequirement):
        assert facts.resource is not None
        evidence = RelationshipEvidenceDTO(
            requirement.source,
            len(facts.relationships) + 1,
            facts.principal.user_id if requirement.require_subject else None,
            facts.resource.resource_type,
            facts.resource.resource_id,
            True,
            facts.resource.scope if requirement.require_scope else None,
            requirement.attributes,
        )
        return replace(facts, relationships=(*facts.relationships, evidence))
    if isinstance(requirement, SessionChannelRequirement):
        channel = next(iter(requirement.channels))
        return replace(
            facts,
            session=SessionContextDTO("request-1", channel, datetime.now(UTC)),
        )
    if isinstance(requirement, ScopeRequirement):
        assert facts.resource is not None
        if requirement.allow_system:
            return replace(
                facts,
                reachable_scopes=ScopeSetDTO(frozenset({ScopeDTO(ScopeType.SYSTEM)})),
            )
        return facts
    if isinstance(requirement, BooleanRequirement):
        return replace(facts, **{requirement.fact.value: requirement.expected})
    if isinstance(requirement, IdentifierReleaseRequirement):
        if (
            facts.resource
            and facts.resource.disclosure_class is DisclosureClass.IDENTIFIER_RELEASE
        ):
            assert facts.resource.scope is not None
            grant = RoleGrantDTO(
                len(facts.role_grants) + 1, Role.PII_EXPORTER, facts.resource.scope
            )
            return replace(
                facts,
                active_roles=facts.active_roles | {Role.PII_EXPORTER},
                role_grants=(*facts.role_grants, grant),
                grant_ids=(*facts.grant_ids, grant.grant_id),
            )
        return facts
    raise AssertionError(f"unhandled requirement {requirement!r}")


def _positive_facts(action: Action) -> EvaluationFactsDTO:
    definition = CATALOGUE[action]
    facts = _base_facts(
        definition.resource_type if definition.requires_resource else None
    )
    if facts.resource is not None:
        facts = replace(
            facts,
            resource=replace(
                facts.resource,
                disclosure_class=definition.disclosure_class,
            ),
        )
    first_path = definition.authorization_paths[0][1]
    return _satisfy(first_path, facts)


def _selected_requirements(value):
    if isinstance(value, Expression):
        children = (
            value.requirements[:1] if value.operator == "any_of" else value.requirements
        )
        return tuple(
            leaf for child in children for leaf in _selected_requirements(child)
        )
    return (value,)


def _omit(requirement, facts: EvaluationFactsDTO) -> EvaluationFactsDTO | None:
    if isinstance(requirement, PublicRequirement):
        return None
    if isinstance(requirement, ActivePrincipalRequirement):
        return replace(facts, principal=replace(facts.principal, active=False))
    if isinstance(requirement, (AnyRoleRequirement, ScopedRoleRequirement)):
        return replace(
            facts,
            active_roles=facts.active_roles - requirement.roles,
            role_grants=tuple(
                grant
                for grant in facts.role_grants
                if grant.role not in requirement.roles
            ),
        )
    if isinstance(requirement, GrantSourceRequirement):
        if GrantSource.AUTHORIZATION_GRANT in requirement.sources:
            return replace(facts, active_roles=frozenset(), role_grants=())
        return replace(
            facts,
            relationships=tuple(
                item
                for item in facts.relationships
                if item.relationship not in requirement.sources
            ),
        )
    if isinstance(requirement, RelationshipRequirement):
        return replace(
            facts,
            relationships=tuple(
                item
                for item in facts.relationships
                if item.relationship is not requirement.source
            ),
        )
    if isinstance(requirement, SessionChannelRequirement):
        return replace(facts, session=None)
    if isinstance(requirement, ScopeRequirement):
        return replace(facts, reachable_scopes=ScopeSetDTO())
    if isinstance(requirement, BooleanRequirement):
        return replace(facts, **{requirement.fact.value: not requirement.expected})
    if isinstance(requirement, IdentifierReleaseRequirement):
        if (
            facts.resource is None
            or facts.resource.disclosure_class is not DisclosureClass.IDENTIFIER_RELEASE
        ):
            return None
        return replace(
            facts,
            active_roles=facts.active_roles - {Role.PII_EXPORTER},
            role_grants=tuple(
                grant
                for grant in facts.role_grants
                if grant.role is not Role.PII_EXPORTER
            ),
        )
    raise AssertionError(f"unhandled requirement {requirement!r}")


def test_legacy_manifest_maps_every_action_exactly_once():
    assert len(ACTION_MIGRATION_MAP) == 121
    assert set(ACTION_MIGRATION_MAP.values()) <= ACTION_MANIFEST
    assert set(CATALOGUE) == set(Action)
    assert len(CATALOGUE) == len(ACTION_MANIFEST) == 153


@pytest.mark.parametrize("action", list(Action), ids=lambda action: action.value)
def test_every_canonical_action_has_a_working_positive_path(action: Action):
    definition = CATALOGUE[action]
    facts = _positive_facts(action)
    decision = check_action(
        action,
        facts,
        resource_type=definition.resource_type
        if definition.requires_resource
        else None,
    )
    assert decision.allowed, action.value
    assert decision.policy_path == definition.authorization_paths[0][0]


@pytest.mark.parametrize(
    "action",
    [
        action
        for action, definition in CATALOGUE.items()
        if definition.authorization_paths[0][0] != "public"
    ],
    ids=lambda action: action.value,
)
def test_every_non_public_action_has_a_negative_path(action: Action):
    definition = CATALOGUE[action]
    facts = _base_facts(
        definition.resource_type if definition.requires_resource else None
    )
    decision = check_action(
        action,
        facts,
        resource_type=definition.resource_type
        if definition.requires_resource
        else None,
    )
    assert not decision.allowed, action.value


@pytest.mark.parametrize(
    "action",
    [
        action
        for action, definition in CATALOGUE.items()
        if definition.requires_resource
    ],
    ids=lambda action: action.value,
)
def test_every_exact_action_denies_when_the_route_omits_its_resource(action: Action):
    facts = _base_facts(None)
    assert not check_action(action, facts, resource_type=None).allowed


@pytest.mark.parametrize(
    "action",
    [
        action
        for action, definition in CATALOGUE.items()
        if definition.requires_resource
    ],
    ids=lambda action: action.value,
)
def test_every_exact_action_denies_when_resolved_lineage_is_missing(action: Action):
    definition = CATALOGUE[action]
    facts = _positive_facts(action)
    assert facts.resource is not None
    facts = replace(facts, resource=replace(facts.resource, scope=None))
    decision = check_action(action, facts, resource_type=definition.resource_type)
    assert not decision.allowed
    assert decision.reason_code == "missing_scope"


@pytest.mark.parametrize("action", list(Action), ids=lambda action: action.value)
def test_every_policy_path_denies_when_any_selected_requirement_is_missing(
    action: Action,
):
    definition = CATALOGUE[action]
    for path_name, expression in definition.authorization_paths:
        facts = _base_facts(
            definition.resource_type if definition.requires_resource else None
        )
        if facts.resource is not None:
            facts = replace(
                facts,
                resource=replace(
                    facts.resource,
                    disclosure_class=definition.disclosure_class,
                ),
            )
        facts = _satisfy(expression, facts)
        assert evaluate(expression, facts), (action.value, path_name)
        for requirement in _selected_requirements(expression):
            missing = _omit(requirement, facts)
            if missing is None:
                continue
            assert not evaluate(expression, missing), (
                action.value,
                path_name,
                requirement,
            )


@pytest.mark.parametrize(
    "values,expected",
    [((True, True), True), ((True, False), False), ((False, False), False)],
)
def test_all_of_truth_table(values, expected):
    class Requirement:
        def __init__(self, value):
            self.value = value

        def __call__(self, _facts):
            return self.value

    assert (
        all_of(*(Requirement(value) for value in values), name="truth")(
            _base_facts(None)
        )
        is expected
    )


@pytest.mark.parametrize(
    "values,expected",
    [((True, True), True), ((True, False), True), ((False, False), False)],
)
def test_any_of_truth_table(values, expected):
    class Requirement:
        def __init__(self, value):
            self.value = value

        def __call__(self, _facts):
            return self.value

    assert (
        any_of(*(Requirement(value) for value in values), name="truth")(
            _base_facts(None)
        )
        is expected
    )


def test_classical_scope_never_reaches_project_lineage():
    hospital = ScopeDTO(ScopeType.HOSPITAL, 10)
    classical_lab = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)
    project_site = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        30,
        hospital_id=10,
        lab_unit_id=20,
        project_id=40,
        project_lab_unit_id=30,
    )
    assert hospital.contains(classical_lab)
    assert not hospital.contains(project_site)
    assert not classical_lab.contains(project_site)


def test_system_scope_is_action_opt_in():
    system = ScopeDTO(ScopeType.SYSTEM)
    project = ScopeDTO(ScopeType.PROJECT, 40, project_id=40)
    assert not system.contains(project)
    assert system.contains(project, allow_system=True)


def test_upload_needs_role_profile_scope_and_active_target():
    action = Action.UPLOAD_CREATE
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    assert check_action(action, allowed, resource_type=definition.resource_type).allowed
    for field in ("target_active",):
        evidence = allowed.relationships[0]
        denied = replace(
            allowed,
            relationships=(
                replace(
                    evidence,
                    attributes=tuple(
                        (key, False if key == field else value)
                        for key, value in evidence.attributes
                    ),
                ),
            ),
        )
        assert not check_action(
            action, denied, resource_type=definition.resource_type
        ).allowed


@pytest.mark.parametrize(
    "role",
    [
        Role.FIELD_OPHTHALMOLOGIST,
        Role.FIELD_OPTOMETRIST,
        Role.OPHTHALMOLOGIST,
        Role.OPTOMETRIST,
    ],
)
def test_mobile_upload_accepts_field_capture_roles_with_exact_profile(role: Role):
    action = Action.MOBILE_UPLOAD_CREATE
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    assert allowed.resource is not None and allowed.resource.scope is not None
    grant = RoleGrantDTO(999, role, allowed.resource.scope)
    allowed = replace(
        allowed,
        active_roles=frozenset({role}),
        role_grants=(grant,),
        grant_ids=(grant.grant_id,),
    )
    assert check_action(action, allowed, resource_type=definition.resource_type).allowed


def test_mobile_upload_does_not_inherit_the_web_file_uploader_role():
    action = Action.MOBILE_UPLOAD_CREATE
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    assert allowed.resource is not None and allowed.resource.scope is not None
    grant = RoleGrantDTO(999, Role.FILE_UPLOADER, allowed.resource.scope)
    denied = replace(
        allowed,
        active_roles=frozenset({Role.FILE_UPLOADER}),
        role_grants=(grant,),
        grant_ids=(grant.grant_id,),
    )
    assert not check_action(
        action, denied, resource_type=definition.resource_type
    ).allowed


def test_grading_requires_each_independent_condition_and_has_no_admin_break_glass():
    action = Action.GRADING_RESIDENT_SUBMIT
    allowed = _positive_facts(action)
    assert Role.ADMIN not in allowed.active_roles
    assert check_action(action, allowed, resource_type="grading_task").allowed
    for field in ("workflow_accepts", "no_conflict", "no_duplicate"):
        evidence = allowed.relationships[0]
        assert not check_action(
            action,
            replace(
                allowed,
                relationships=(
                    replace(
                        evidence,
                        attributes=tuple(
                            (key, False if key == field else value)
                            for key, value in evidence.attributes
                        ),
                    ),
                ),
            ),
            resource_type="grading_task",
        ).allowed
    admin = replace(
        allowed,
        active_roles=frozenset({Role.ADMIN}),
        role_grants=(RoleGrantDTO(999, Role.ADMIN, allowed.resource.scope),),
    )
    assert not check_action(action, admin, resource_type="grading_task").allowed


def test_identifier_release_requires_additive_pii_role():
    action = Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    assert allowed.resource is not None
    release = allowed.resource
    without_pii = replace(
        allowed,
        resource=release,
        active_roles=allowed.active_roles - {Role.PII_EXPORTER},
        role_grants=tuple(
            grant
            for grant in allowed.role_grants
            if grant.role is not Role.PII_EXPORTER
        ),
    )
    assert not check_action(
        action, without_pii, resource_type=definition.resource_type
    ).allowed
    assert release.scope is not None
    with_pii = replace(
        without_pii,
        active_roles=without_pii.active_roles | {Role.PII_EXPORTER},
        role_grants=(
            *without_pii.role_grants,
            RoleGrantDTO(999, Role.PII_EXPORTER, release.scope),
        ),
    )
    assert check_action(
        action, with_pii, resource_type=definition.resource_type
    ).allowed


@pytest.mark.parametrize(
    "action",
    [
        Action.MOBILE_CONTEXT_VIEW,
        Action.MOBILE_FIELD_PROJECTS_LIST,
        Action.MOBILE_FIELD_PROJECT_VIEW,
        Action.MOBILE_FIELD_PROJECT_SYNC,
        Action.MOBILE_FIELD_ENCOUNTER_VIEW,
        Action.MOBILE_FIELD_ENCOUNTER_CAPTURE,
        Action.MOBILE_FIELD_INFERENCE_RUN,
        Action.MOBILE_SESSION_LIST,
        Action.MOBILE_SESSION_DETAIL_VIEW,
        Action.MOBILE_SESSION_REVOKE,
        Action.MOBILE_UPLOAD_CREATE,
        Action.MOBILE_UPLOAD_OPTIONS_VIEW,
        Action.MOBILE_UPLOAD_VIEW,
        Action.MOBILE_UPLOAD_INFERENCE_RETRY,
    ],
)
def test_mobile_actions_require_mobile_session_channel(action: Action):
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    assert allowed.session is not None
    web = replace(
        allowed,
        session=replace(allowed.session, channel=SessionChannel.WEB),
    )
    assert not check_action(
        action,
        web,
        resource_type=definition.resource_type
        if definition.requires_resource
        else None,
    ).allowed


@pytest.mark.parametrize(
    "action",
    [
        Action.MOBILE_FIELD_PROJECTS_LIST,
        Action.MOBILE_FIELD_PROJECT_VIEW,
        Action.MOBILE_FIELD_PROJECT_SYNC,
    ],
)
def test_project_oversight_roles_do_not_imply_mobile_field_operation(action: Action):
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    pi_only = replace(
        allowed,
        active_roles=frozenset({Role.PROJECT_PI}),
        role_grants=tuple(
            replace(grant, role=Role.PROJECT_PI) for grant in allowed.role_grants[:1]
        ),
    )
    assert not check_action(
        action,
        pi_only,
        resource_type=definition.resource_type
        if definition.requires_resource
        else None,
    ).allowed


@pytest.mark.parametrize(
    "action",
    [
        Action.AUTH_PASSWORD_RESET_COMPLETE,
        Action.DATASET_PUBLIC_DOWNLOAD,
        Action.AUTH_MOBILE_REFRESH,
        Action.AUTH_MOBILE_LOGOUT,
    ],
)
def test_signed_credentials_cannot_be_replayed_from_a_web_session(action: Action):
    definition = CATALOGUE[action]
    allowed = _positive_facts(action)
    assert allowed.session is not None
    assert allowed.session.channel is SessionChannel.SIGNED
    web = replace(allowed, session=replace(allowed.session, channel=SessionChannel.WEB))
    assert not check_action(action, web, resource_type=definition.resource_type).allowed


def test_self_actions_cannot_be_satisfied_by_admin():
    action = Action.ACCOUNT_PROFILE_UPDATE
    allowed = _positive_facts(action)
    assert check_action(action, allowed, resource_type="user").allowed
    admin = replace(allowed, self_identity=False, active_roles=frozenset({Role.ADMIN}))
    assert not check_action(action, admin, resource_type="user").allowed


def test_role_scope_and_delegation_rules_are_explicit():
    assert role_accepts_scope(Role.USER_MANAGER, ScopeType.HOSPITAL)
    assert not role_accepts_scope(Role.USER_MANAGER, ScopeType.PROJECT)
    assert may_delegate(Role.ADMIN, Role.PROJECT_PI)
    assert may_delegate(Role.ADMIN, Role.SITE_PI)
    assert not may_delegate(Role.PROJECT_ADMIN, Role.PROJECT_PI)
    assert not may_delegate(Role.PROJECT_ADMIN, Role.SITE_PI)
    assert not may_delegate(Role.PROJECT_ADMIN, Role.PROJECT_ADMIN)
    assert may_delegate(Role.PROJECT_PI, Role.PROJECT_ADMIN)
    assert may_delegate(Role.SITE_PI, Role.PROJECT_ADMIN)
    assert role_accepts_scope(Role.PROJECT_ADMIN, ScopeType.PROJECT)
    assert role_accepts_scope(Role.PROJECT_ADMIN, ScopeType.PROJECT_LAB_UNIT)
    assert not may_delegate(Role.LOCAL_ADMIN, Role.USER_MANAGER)
    assert set(ROLE_CONTRACTS) == set(Role)


@pytest.mark.parametrize(
    ("role", "scope"),
    [
        (Role.PROJECT_PI, ScopeDTO(ScopeType.PROJECT, 40, project_id=40)),
        (
            Role.SITE_PI,
            ScopeDTO(
                ScopeType.PROJECT_LAB_UNIT,
                30,
                hospital_id=10,
                lab_unit_id=20,
                project_id=40,
                project_lab_unit_id=30,
            ),
        ),
    ],
)
def test_project_and_site_pi_can_enter_grant_management(role: Role, scope: ScopeDTO):
    for action in (
        Action.AUTHORIZATION_GRANTS_VIEW,
        Action.AUTHORIZATION_GRANTS_MANAGE,
    ):
        definition = CATALOGUE[action]
        facts = _positive_facts(action)
        grant = RoleGrantDTO(999, role, scope)
        facts = replace(
            facts,
            active_roles=frozenset({role}),
            role_grants=(grant,),
            grant_ids=(grant.grant_id,),
            reachable_scopes=ScopeSetDTO(frozenset({scope})),
            resource=(
                replace(facts.resource, scope=scope)
                if facts.resource is not None
                else None
            ),
        )
        assert check_action(
            action,
            facts,
            resource_type=definition.resource_type
            if definition.requires_resource
            else None,
        ).allowed


def test_core_has_no_framework_or_orm_imports():
    banned = {"flask", "sqlalchemy", "redis", "models", "app"}
    core_dir = Path(__file__).parents[4] / "authz_v2" / "core"
    for path in core_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            assert not roots & banned, f"{path} imports {roots & banned}"
