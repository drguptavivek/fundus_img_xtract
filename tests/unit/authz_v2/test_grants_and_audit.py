from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from authz_v2.core.decisions import AuthorizationReceiptDTO
from authz_v2.core.principals import (
    PrincipalDTO,
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.grants import (
    GrantCreateDTO,
    GrantUpdateDTO,
    normalize_description,
    validate_grant_target,
)
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.repositories.grants import GrantRepository
from authz_v2.services.audit import AuthorizationAuditService
from authz_v2.services.grants import GrantMutationService
from models import LabUnit
from project_configuration.models import ProjectLabUnit


class CapturingAuditRepository:
    def __init__(self) -> None:
        self.rows = []

    def append(self, event):
        self.rows.append(event)
        return event


class AllowingDecisionService:
    def authoritative_principal(self, principal):
        return principal

    def require(self, _db, principal, action, _resource):
        return AuthorizationReceiptDTO(
            action.value,
            "grant_target",
            "target",
            "scoped_role",
            request_id=principal.session.request_id if principal.session else None,
        )


class CapturingAuditService:
    def __init__(self):
        self.calls = []

    def record_allowed(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def test_grant_description_and_target_validation_fail_closed():
    assert normalize_description("  reason  ") == "reason"
    assert normalize_description("  ") is None
    with pytest.raises(ValueError):
        normalize_description("x" * 501)
    validate_grant_target(
        Role.FILE_UPLOADER,
        ScopeDTO(ScopeType.LAB_UNIT, 2, hospital_id=1, lab_unit_id=2),
    )
    with pytest.raises(ValueError):
        validate_grant_target(
            Role.USER_MANAGER, ScopeDTO(ScopeType.PROJECT, 3, project_id=3)
        )
    with pytest.raises(ValueError):
        validate_grant_target(Role.FILE_UPLOADER, ScopeDTO(ScopeType.LAB_UNIT, 2))


def test_audit_allowlists_details_and_denials_omit_resource_identifiers():
    repository = CapturingAuditRepository()
    audit = AuthorizationAuditService(repository)
    session = SessionContextDTO("request-1", SessionChannel.WEB, datetime.now(UTC))
    principal = PrincipalDTO(1, True, True, session)
    receipt = AuthorizationReceiptDTO(
        "dataset.export.download",
        "dataset_export",
        44,
        "scoped_data_export",
        request_id="request-1",
    )
    resource = ResourceContextDTO(
        "dataset_export",
        44,
        ScopeDTO(ScopeType.PROJECT, 3, project_id=3),
    )
    allowed = audit.record_allowed(
        event="dataset_export",
        principal=principal,
        receipt=receipt,
        resource=resource,
        details={"result_count": 2, "token": "secret", "filename": "patient.jpg"},
    )
    assert json.loads(allowed.detail_json) == {"result_count": 2}
    assert allowed.resource_id == "44"
    denied = audit.record_denied(
        event="dataset_export", action=receipt.action, principal=principal
    )
    assert denied.resource_id is None
    assert denied.scope_id is None
    assert denied.detail_json is None


def test_audit_changed_fields_records_names_only_and_rejects_nested_secrets():
    repository = CapturingAuditRepository()
    audit = AuthorizationAuditService(repository)
    principal = PrincipalDTO(1, True, True)
    receipt = AuthorizationReceiptDTO("project.access.manage", "project", 3, "path")
    row = audit.record_allowed(
        event="grant_update",
        principal=principal,
        receipt=receipt,
        details={"changed_fields": {"description": "must-not-persist"}},
    )
    assert json.loads(row.detail_json) == {"changed_fields": ["description"]}
    with pytest.raises(ValueError, match="changed_fields"):
        audit.record_allowed(
            event="grant_update",
            principal=principal,
            receipt=receipt,
            details={"changed_fields": {"token": {"secret": "value"}}},
        )


def test_grant_creation_uses_stored_project_site_lineage():
    project_scope = ScopeDTO(ScopeType.PROJECT, 10, project_id=10)

    class FakeDb:
        def get(self, model, identity):
            if model is ProjectLabUnit and identity == 999:
                return SimpleNamespace(id=999, project_id=11, lab_unit_id=20)
            if model is LabUnit and identity == 20:
                return SimpleNamespace(id=20, hospital_id=1)
            return None

    class Repository:
        db = FakeDb()

        def resolve_scope(self, scope):
            return GrantRepository.resolve_scope(self, scope)

        def grants_for(self, user_id):
            return (GrantRecord(1, user_id, Role.PROJECT_ADMIN, project_scope, True),)

    service = GrantMutationService(
        Repository(), AllowingDecisionService(), CapturingAuditService()
    )
    forged = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        999,
        project_id=10,
        lab_unit_id=20,
        project_lab_unit_id=999,
    )
    with pytest.raises(PermissionError, match="not_authorized"):
        service.create(
            PrincipalDTO(1, True, True),
            GrantCreateDTO(2, Role.COLLABORATOR, forged),
        )


def test_pi_project_admin_delegation_is_confined_to_the_pi_scope():
    project_10 = ScopeDTO(ScopeType.PROJECT, 10, project_id=10)
    project_11 = ScopeDTO(ScopeType.PROJECT, 11, project_id=11)
    site_100 = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        100,
        project_id=10,
        lab_unit_id=20,
        project_lab_unit_id=100,
    )
    site_101 = ScopeDTO(
        ScopeType.PROJECT_LAB_UNIT,
        101,
        project_id=10,
        lab_unit_id=21,
        project_lab_unit_id=101,
    )

    class FakeDb:
        def flush(self):
            return None

    class Repository:
        db = FakeDb()

        def __init__(self, actor_role, actor_scope):
            self.actor_role = actor_role
            self.actor_scope = actor_scope

        def resolve_scope(self, scope):
            return scope

        def grants_for(self, user_id):
            return (GrantRecord(1, user_id, self.actor_role, self.actor_scope, True),)

        def role_id(self, _role):
            return 4

        def find_historical(self, **_kwargs):
            return None

        def add(self, grant):
            grant.id = 9
            return grant

    def service_for(role, scope):
        return GrantMutationService(
            Repository(role, scope), AllowingDecisionService(), CapturingAuditService()
        )

    project_pi = service_for(Role.PROJECT_PI, project_10)
    project_pi.create(
        PrincipalDTO(1, True, True),
        GrantCreateDTO(2, Role.PROJECT_ADMIN, project_10),
    )
    project_pi.create(
        PrincipalDTO(1, True, True),
        GrantCreateDTO(2, Role.PROJECT_ADMIN, site_100),
    )
    with pytest.raises(PermissionError, match="not_authorized"):
        project_pi.create(
            PrincipalDTO(1, True, True),
            GrantCreateDTO(2, Role.PROJECT_ADMIN, project_11),
        )

    site_pi = service_for(Role.SITE_PI, site_100)
    site_pi.create(
        PrincipalDTO(1, True, True),
        GrantCreateDTO(2, Role.PROJECT_ADMIN, site_100),
    )
    for forbidden_scope in (project_10, site_101):
        with pytest.raises(PermissionError, match="not_authorized"):
            site_pi.create(
                PrincipalDTO(1, True, True),
                GrantCreateDTO(2, Role.PROJECT_ADMIN, forbidden_scope),
            )


@pytest.mark.parametrize(
    "target_role", [Role.PROJECT_PI, Role.SITE_PI, Role.PROJECT_ADMIN]
)
def test_project_admin_cannot_delegate_governance_roles(target_role: Role):
    scope = ScopeDTO(ScopeType.PROJECT, 10, project_id=10)

    class Repository:
        def grants_for(self, user_id):
            return (GrantRecord(1, user_id, Role.PROJECT_ADMIN, scope, True),)

    service = GrantMutationService(
        Repository(), AllowingDecisionService(), CapturingAuditService()
    )
    with pytest.raises(PermissionError, match="not_authorized"):
        service._require_delegation(1, target_role, scope)


def test_grant_description_can_be_explicitly_cleared():
    grant = SimpleNamespace(
        id=3,
        user_id=2,
        role_id=4,
        description="old reason",
        active=True,
        updated_by_user_id=None,
        updated_at=None,
    )

    class FakeDb:
        def flush(self):
            return None

    class Repository:
        db = FakeDb()

        def get_for_update(self, grant_id):
            return grant if grant_id == grant.id else None

        def role_for(self, role_id):
            return Role.COLLABORATOR

        def scope_for(self, _grant):
            return ScopeDTO(ScopeType.PROJECT, 10, project_id=10)

        def grants_for(self, user_id):
            return (
                GrantRecord(
                    1,
                    user_id,
                    Role.PROJECT_ADMIN,
                    ScopeDTO(ScopeType.PROJECT, 10, project_id=10),
                    True,
                ),
            )

    audit = CapturingAuditService()
    GrantMutationService(Repository(), AllowingDecisionService(), audit).update(
        PrincipalDTO(1, True, True), 3, GrantUpdateDTO(description=None)
    )
    assert grant.description is None
    assert audit.calls[0]["details"]["changed_fields"] == ("description",)


def test_mandatory_audit_failure_propagates_without_service_commit():
    scope = ScopeDTO(ScopeType.PROJECT, 10, project_id=10)

    class FakeDb:
        committed = False

        def flush(self):
            return None

    class Repository:
        db = FakeDb()

        def resolve_scope(self, _scope):
            return scope

        def grants_for(self, user_id):
            return (GrantRecord(1, user_id, Role.PROJECT_ADMIN, scope, True),)

        def role_id(self, _role):
            return 4

        def find_historical(self, **_kwargs):
            return None

        def add(self, grant):
            grant.id = 9
            self.db.flush()
            return grant

    class FailingAudit:
        def record_allowed(self, **_kwargs):
            raise RuntimeError("audit unavailable")

    service = GrantMutationService(
        Repository(), AllowingDecisionService(), FailingAudit()
    )
    with pytest.raises(RuntimeError, match="audit unavailable"):
        service.create(
            PrincipalDTO(1, True, True),
            GrantCreateDTO(2, Role.COLLABORATOR, scope),
        )
    assert not service.repository.db.committed
