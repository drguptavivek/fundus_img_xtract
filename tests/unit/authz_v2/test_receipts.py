from dataclasses import replace
from datetime import UTC, datetime

from authz_v2.core.actions import Action
from authz_v2.core.principals import (
    GrantSource,
    PrincipalDTO,
    RelationshipEvidenceDTO,
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.resources.registry import (
    ResourceAdapter,
    ResourceRegistry,
    ResourceTarget,
)
from authz_v2.services.decision import AuthorizationDecisionService

SCOPE = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)


class Repository:
    def principal(self, user_id):
        return PrincipalDTO(user_id, True, True)

    def grants_for(self, user_id):
        return (GrantRecord(7, user_id, Role.FILE_UPLOADER, SCOPE, True),)


def test_receipt_contains_typed_scope_and_selected_relationship_evidence():
    def resolve(_db, resource_id):
        return ResourceTarget(
            object(), ResourceContextDTO("upload_target", resource_id, SCOPE)
        )

    def facts(_db, _principal, _action, _target, base):
        selected = RelationshipEvidenceDTO(
            GrantSource.UPLOAD_PROFILE,
            51,
            1,
            "upload_target",
            10,
            True,
            SCOPE,
            (("target_active", True),),
        )
        unrelated = replace(
            selected,
            relationship=GrantSource.PARTICIPATION,
            evidence_id=99,
        )
        return replace(base, relationships=(selected, unrelated))

    registry = ResourceRegistry()
    registry.register(
        ResourceAdapter(
            "upload_target",
            resolve,
            lambda _db, _principal, _action, _grants, query: query,
            facts,
        )
    )
    session = SessionContextDTO("request", SessionChannel.WEB, datetime.now(UTC))
    principal = PrincipalDTO(1, True, True, session)
    receipt = AuthorizationDecisionService(Repository(), registry).require(
        None, principal, Action.UPLOAD_CREATE, 10
    )
    assert receipt.scope == SCOPE
    assert tuple(item.evidence_id for item in receipt.relationship_evidence) == (51,)
