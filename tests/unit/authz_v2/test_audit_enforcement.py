from datetime import UTC, datetime

import pytest

from authz_v2.core.actions import Action
from authz_v2.core.decisions import DecisionDTO
from authz_v2.core.principals import PrincipalDTO, SessionChannel, SessionContextDTO
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import ScopeType
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.resources.registry import ResourceRegistry, ResourceTarget
from authz_v2.services.decision import AuthorizationDecisionService

SCOPE = ScopeDTO(ScopeType.PROJECT, 4, project_id=4)


class Repository:
    def principal(self, user_id):
        return PrincipalDTO(user_id, True, True)

    def grants_for(self, _user_id):
        return ()


class AllowedService(AuthorizationDecisionService):
    def __init__(self, action, path="scoped_role"):
        super().__init__(Repository(), ResourceRegistry())
        self.action = action
        self.path = path

    def _evaluate_with_metrics(self, _db, _principal, _action, _resource):
        target = ResourceTarget(
            object(), ResourceContextDTO("dataset", 7, SCOPE, resolved=True)
        )
        return DecisionDTO(True, self.action.value, "allowed", self.path), target


class Audit:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def record_allowed(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("audit unavailable")


def _principal():
    session = SessionContextDTO("request", SessionChannel.WEB, datetime.now(UTC))
    return PrincipalDTO(1, True, True, session)


def test_mandatory_action_denies_when_no_durable_audit_sink_is_supplied():
    service = AllowedService(Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS)
    with pytest.raises(AuthorizationError) as error:
        service.require(None, _principal(), service.action, 7)
    assert error.value.code is DenialCode.AUDIT_REQUIRED
    audit = Audit()
    service.require(None, _principal(), service.action, 7, audit_service=audit)
    assert audit.calls[0]["event"] == "authorization_allow"


def test_mandatory_audit_failure_blocks_authorized_operation():
    service = AllowedService(Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        service.require(
            None, _principal(), service.action, 7, audit_service=Audit(fail=True)
        )


def test_break_glass_is_mandatory_audited_even_for_optional_audit_action():
    service = AllowedService(Action.DATASET_CURATION_VIEW, path="admin_break_glass")
    with pytest.raises(AuthorizationError) as error:
        service.require(None, _principal(), service.action, 7)
    assert error.value.code is DenialCode.AUDIT_REQUIRED
