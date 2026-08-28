from __future__ import annotations

from authz_v2.core.actions import Action
from authz_v2.core.catalogue import check_action
from authz_v2.core.principals import (
    EvaluationFactsDTO,
    GrantSource,
    PrincipalDTO,
    RelationshipEvidenceDTO,
    RoleGrantDTO,
)
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO, ScopeSetDTO
from authz_v2.core.roles import Role, ScopeType

SITE = ScopeDTO(
    ScopeType.PROJECT_LAB_UNIT,
    30,
    lab_unit_id=20,
    project_id=40,
    project_lab_unit_id=30,
)


def facts(action: Action, role: Role, *, relationship=None):
    from authz_v2.core.catalogue import CATALOGUE

    definition = CATALOGUE[action]
    resource = ResourceContextDTO(
        definition.resource_type,
        7,
        SITE,
        disclosure_class=definition.disclosure_class,
        state={"domain_valid": True},
    )
    grant = RoleGrantDTO(1, role, SITE)
    return EvaluationFactsDTO(
        PrincipalDTO(1, True, True),
        resource=resource,
        active_roles=frozenset({role}),
        role_grants=(grant,),
        reachable_scopes=ScopeSetDTO(frozenset({SITE})),
        relationships=(relationship,) if relationship else (),
        exact_resource=True,
        domain_valid=True,
    )


def decide(action: Action, value: EvaluationFactsDTO):
    from authz_v2.core.catalogue import CATALOGUE

    definition = CATALOGUE[action]
    return check_action(action, value, resource_type=definition.resource_type)


def screen_facts(role: Role) -> EvaluationFactsDTO:
    scope = (
        ScopeDTO(ScopeType.SYSTEM)
        if role is Role.ADMIN
        else ScopeDTO(ScopeType.HOSPITAL, 10, hospital_id=10)
    )
    grant = RoleGrantDTO(1, role, scope)
    return EvaluationFactsDTO(
        PrincipalDTO(1, True, True),
        active_roles=frozenset({role}),
        role_grants=(grant,),
        reachable_scopes=ScopeSetDTO(frozenset({scope})),
    )


def test_verification_is_not_inherited_by_data_manager():
    action = Action.VERIFICATION_DIRECT_UPDATE
    assert decide(action, facts(action, Role.VERIFIER)).allowed
    assert not decide(action, facts(action, Role.DATA_MANAGER)).allowed


def test_admin_security_diagnostics_are_admin_only():
    action = Action.ADMIN_SECURITY_VIEW
    assert decide(action, screen_facts(Role.ADMIN)).allowed
    for role in (
        Role.LOCAL_ADMIN,
        Role.PROJECT_PI,
        Role.SITE_PI,
        Role.PROJECT_ADMIN,
    ):
        assert not decide(action, screen_facts(role)).allowed


def test_admin_user_workspace_admits_only_admin_and_local_admin():
    action = Action.ADMIN_USERS_WORKSPACE_VIEW
    assert decide(action, screen_facts(Role.ADMIN)).allowed
    assert decide(action, screen_facts(Role.LOCAL_ADMIN)).allowed
    for role in (Role.PROJECT_PI, Role.SITE_PI, Role.PROJECT_ADMIN):
        assert not decide(action, screen_facts(role)).allowed


def test_pregraded_upload_is_distinct_from_capture_upload():
    action = Action.PROJECT_UPLOAD_PREGRADED
    evidence = RelationshipEvidenceDTO(
        GrantSource.UPLOAD_PROFILE,
        5,
        1,
        "project_upload_target",
        7,
        True,
        SITE,
        (("target_active", True),),
    )
    assert decide(
        action, facts(action, Role.PREGRADED_UPLOADER, relationship=evidence)
    ).allowed
    assert not decide(
        action, facts(action, Role.FILE_UPLOADER, relationship=evidence)
    ).allowed


def test_field_ophthalmologist_can_grade_but_admin_cannot_break_glass():
    action = Action.GRADING_RESIDENT_SUBMIT
    relationship = RelationshipEvidenceDTO(
        GrantSource.GRADING_SLOT,
        "7:resident",
        1,
        "grading_task",
        7,
        True,
        SITE,
        (("allocation_enforced", False),),
    )
    assert decide(
        action, facts(action, Role.FIELD_OPHTHALMOLOGIST, relationship=relationship)
    ).allowed
    assert not decide(
        action, facts(action, Role.ADMIN, relationship=relationship)
    ).allowed


def test_dataset_release_is_not_dataset_creation_authority():
    action = Action.DATASET_EXPORT_CREATE
    assert decide(action, facts(action, Role.DATA_EXPORTER)).allowed
    assert not decide(action, facts(action, Role.DATASET_CREATOR)).allowed


def test_cross_site_and_cross_project_scope_do_not_contain_target():
    other_site = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        31,
        lab_unit_id=21,
        project_id=40,
        project_lab_unit_id=31,
    )
    other_project = ScopeDTO(ScopeType.PROJECT, 41, project_id=41)
    assert not other_site.contains(SITE)
    assert not other_project.contains(SITE)


def test_project_upload_manager_roles_cannot_cross_project_or_site_scope():
    action = Action.PROJECT_UPLOADERS_MANAGE
    for role in (Role.PROJECT_PI, Role.SITE_PI, Role.PROJECT_ADMIN):
        assert decide(action, facts(action, role)).allowed

        value = facts(action, role)
        other_project = ScopeDTO(ScopeType.PROJECT, 41, project_id=41)
        crossed = EvaluationFactsDTO(
            value.principal,
            resource=value.resource,
            active_roles=value.active_roles,
            role_grants=(RoleGrantDTO(2, role, other_project),),
            reachable_scopes=ScopeSetDTO(frozenset({other_project})),
            exact_resource=True,
            domain_valid=True,
        )
        assert not decide(action, crossed).allowed
