from __future__ import annotations

from authz_v2.core.actions import Action
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.models import AuthorizationUploadProfileAssignment
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.services.projections import capability_projection, upload_projection
from models import (
    LabUnit,
    Project,
    ProjectLabUnit,
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
)


class Result:
    def __init__(self, values=()):
        self.values = tuple(values)

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self.values)


class QueueDB:
    def __init__(self, *values):
        self.values = list(values)

    def execute(self, _query):
        return Result(self.values.pop(0))


def test_capabilities_are_potential_only_and_include_self_actions():
    principal = PrincipalDTO(1, True, True)
    lab = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)
    grants = (GrantRecord(1, 1, Role.VERIFIER, lab, True),)
    projection = capability_projection(principal, grants)
    names = {item.action for item in projection}
    assert Action.ACCOUNT_PROFILE_VIEW.value in names
    assert Action.VERIFICATION_DIRECT_UPDATE.value in names
    assert Action.DATASET_EXPORT_CREATE.value not in names
    assert all(item.allowed for item in projection)


def test_identifier_release_capability_requires_overlapping_additive_pii_grant():
    principal = PrincipalDTO(1, True, True)
    lab = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)
    export = GrantRecord(1, 1, Role.DATA_EXPORTER, lab, True)
    names = {item.action for item in capability_projection(principal, (export,))}
    assert Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS.value not in names

    pii = GrantRecord(2, 1, Role.PII_EXPORTER, lab, True)
    names = {item.action for item in capability_projection(principal, (export, pii))}
    assert Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS.value in names


def _upload_projection_db(*, project_active: bool = True):
    classical_scope = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)
    project_scope = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        30,
        hospital_id=10,
        lab_unit_id=20,
        project_id=40,
        project_lab_unit_id=30,
    )
    classical = AuthorizationUploadProfileAssignment(
        id=1, user_id=1, lab_unit_id=20, upload_profile_id=9, active=True
    )
    project_assignment = ProjectUploadProfileAssignment(
        id=2,
        user_id=1,
        lab_unit_id=20,
        project_upload_profile_id=71,
        active=True,
    )
    mapping = ProjectUploadProfile(
        id=71, project_id=40, upload_profile_id=9, active=True
    )
    profile = UploadProfile(id=9, name="Capture", active=True)
    lab = LabUnit(id=20, name="Site A", hospital_id=10)
    project = Project(id=40, title="Study", active=project_active)
    site = ProjectLabUnit(id=30, project_id=40, lab_unit_id=20, active=True)
    return (
        QueueDB(
            (classical,),
            (project_assignment,),
            (mapping,),
            (profile,),
            (lab,),
            (project,),
            (site,),
        ),
        classical_scope,
        project_scope,
    )


def test_upload_options_expose_authorized_profile_identity_not_configuration():
    principal = PrincipalDTO(1, True, True)
    db, classical_scope, project_scope = _upload_projection_db()
    grants = (
        GrantRecord(1, 1, Role.FILE_UPLOADER, classical_scope, True),
        GrantRecord(2, 1, Role.FILE_UPLOADER, project_scope, True),
    )
    options = upload_projection(db, principal, grants)
    assert {item.id for item in options} == {"classical:1", "project:2"}
    assert {item.upload_profile_id for item in options} == {9}
    assert all(not hasattr(item, "upload_kinds") for item in options)


def test_upload_options_require_an_upload_role_grant_in_the_exact_scope():
    principal = PrincipalDTO(1, True, True)
    db, classical_scope, project_scope = _upload_projection_db()
    grants = (
        GrantRecord(1, 1, Role.ANALYTICS_VIEWER, classical_scope, True),
        GrantRecord(2, 1, Role.FILE_UPLOADER, project_scope, True),
    )
    options = upload_projection(db, principal, grants)
    assert {item.id for item in options} == {"project:2"}


def test_upload_options_hide_assignments_for_an_inactive_project():
    principal = PrincipalDTO(1, True, True)
    db, _classical_scope, project_scope = _upload_projection_db(project_active=False)
    grants = (GrantRecord(2, 1, Role.FILE_UPLOADER, project_scope, True),)
    options = upload_projection(db, principal, grants)
    assert options == ()
