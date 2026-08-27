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


def test_verification_is_not_inherited_by_data_manager():
    action = Action.VERIFICATION_DIRECT_UPDATE
    assert decide(action, facts(action, Role.VERIFIER)).allowed
    assert not decide(action, facts(action, Role.DATA_MANAGER)).allowed


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
        (
            ("workflow_accepts", True),
            ("no_conflict", True),
            ("no_duplicate", True),
            ("allocation_enforced", False),
        ),
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
