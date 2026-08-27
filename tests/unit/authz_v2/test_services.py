from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from authz_v2.core.actions import Action
from authz_v2.core.choices import ChoiceListDTO
from authz_v2.core.principals import (
    GrantSource,
    PrincipalDTO,
    RelationshipEvidenceDTO,
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.resources.registry import (
    ChoiceRegistry,
    ResourceAdapter,
    ResourceRegistry,
    ResourceTarget,
)
from authz_v2.resources.users import USER_ADAPTER
from authz_v2.services.choices import list_choices
from authz_v2.services.decision import AuthorizationDecisionService
from authz_v2.services.listing import filter_query
from authz_v2.telemetry.metrics import duration_snapshot, snapshot
from models import User

LAB_SCOPE = ScopeDTO(ScopeType.LAB_UNIT, 20, hospital_id=10, lab_unit_id=20)


class FakeRepository:
    def __init__(
        self, *, active: bool = True, grants: tuple[GrantRecord, ...] = ()
    ) -> None:
        self.active = active
        self.grants = grants

    def principal(self, user_id: int) -> PrincipalDTO | None:
        return PrincipalDTO(user_id, active=self.active, authenticated=True)

    def grants_for(self, user_id: int) -> tuple[GrantRecord, ...]:
        return tuple(grant for grant in self.grants if grant.user_id == user_id)


def principal(user_id: int = 1) -> PrincipalDTO:
    session = SessionContextDTO("request-1", SessionChannel.WEB, datetime.now(UTC))
    return PrincipalDTO(user_id, active=True, authenticated=True, session=session)


def user_adapter() -> ResourceAdapter:
    def resolve(_db, resource_id):
        if resource_id not in {1, 2}:
            return None
        context = ResourceContextDTO("user", resource_id, LAB_SCOPE, resolved=True)
        return ResourceTarget({"id": resource_id}, context)

    return ResourceAdapter(
        "user", resolve, lambda _db, _principal, _action, _grants, query: query
    )


def upload_adapter() -> ResourceAdapter:
    def resolve(_db, resource_id):
        if resource_id != 10:
            return None
        return ResourceTarget(
            {"id": resource_id},
            ResourceContextDTO("upload_target", resource_id, LAB_SCOPE, resolved=True),
        )

    def facts(_db, _principal, _action, _target, base):
        assert base.resource is not None
        return replace(
            base,
            relationships=(
                RelationshipEvidenceDTO(
                    GrantSource.UPLOAD_PROFILE,
                    50,
                    base.principal.user_id,
                    base.resource.resource_type,
                    base.resource.resource_id,
                    True,
                    base.resource.scope,
                    (("target_active", True),),
                ),
            ),
        )

    return ResourceAdapter(
        "upload_target",
        resolve,
        lambda _db, _principal, _action, _grants, query: query,
        facts,
    )


def dataset_adapter() -> ResourceAdapter:
    def resolve(_db, resource_id):
        if resource_id != 10:
            return None
        return ResourceTarget(
            {"id": resource_id},
            ResourceContextDTO("dataset", resource_id, LAB_SCOPE, resolved=True),
        )

    def facts(_db, _principal, _action, _target, base):
        return replace(base, domain_valid=True)

    return ResourceAdapter(
        "dataset",
        resolve,
        lambda _db, _principal, _action, _grants, query: query,
        facts,
    )


def service(
    repository: FakeRepository, *adapters: ResourceAdapter
) -> AuthorizationDecisionService:
    resources = ResourceRegistry()
    for adapter in adapters:
        resources.register(adapter)
    return AuthorizationDecisionService(repository, resources)


def test_self_action_uses_server_resolved_identity_and_returns_receipt():
    authz = service(FakeRepository(), user_adapter())
    assert authz.check(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1).allowed
    assert not authz.check(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 2).allowed
    receipt = authz.require(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1)
    assert receipt.resource_id == 1
    assert receipt.policy_path == "self"
    assert receipt.request_id == "request-1"


def test_decision_metrics_are_recorded_without_becoming_authoritative(monkeypatch):
    authz = service(FakeRepository(), user_adapter())
    before = snapshot().get(
        ("authz_decisions_total", Action.ACCOUNT_PROFILE_VIEW.value, "allow"), 0
    )
    assert authz.check(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1).allowed
    assert (
        snapshot()[
            ("authz_decisions_total", Action.ACCOUNT_PROFILE_VIEW.value, "allow")
        ]
        == before + 1
    )
    assert duration_snapshot()[Action.ACCOUNT_PROFILE_VIEW.value][0] >= 1

    monkeypatch.setattr(
        "authz_v2.services.decision.increment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("metrics down")),
    )
    assert authz.check(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1).allowed


def test_scoped_role_and_upload_profile_must_both_match():
    grant = GrantRecord(7, 1, Role.FILE_UPLOADER, LAB_SCOPE, True)
    irrelevant = GrantRecord(8, 1, Role.ANALYTICS_VIEWER, LAB_SCOPE, True)
    authz = service(FakeRepository(grants=(grant, irrelevant)), upload_adapter())
    decision = authz.check(None, principal(), Action.UPLOAD_CREATE, 10)
    assert decision.allowed
    assert decision.policy_path == "scoped_upload_profile"
    assert decision.evidence == (7,)

    wrong_scope = ScopeDTO(ScopeType.LAB_UNIT, 21, hospital_id=10, lab_unit_id=21)
    denied = service(
        FakeRepository(grants=(replace(grant, scope=wrong_scope),)),
        upload_adapter(),
    ).check(None, principal(), Action.UPLOAD_CREATE, 10)
    assert not denied.allowed


def test_identifier_release_requires_additive_pii_grant_at_runtime():
    export = GrantRecord(7, 1, Role.DATA_EXPORTER, LAB_SCOPE, True)
    pii = GrantRecord(8, 1, Role.PII_EXPORTER, LAB_SCOPE, True)
    without_pii = service(FakeRepository(grants=(export,)), dataset_adapter()).check(
        None, principal(), Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS, 10
    )
    assert not without_pii.allowed
    with_pii = service(FakeRepository(grants=(export, pii)), dataset_adapter()).check(
        None, principal(), Action.DATASET_EXPORT_DOWNLOAD_IDENTIFIERS, 10
    )
    assert with_pii.allowed


def test_unknown_action_resource_and_inactive_principal_deny_closed():
    authz = service(FakeRepository(), user_adapter())
    assert (
        authz.check(None, principal(), "missing.action", None).reason_code
        == "unknown_action"
    )
    no_adapter = service(FakeRepository())
    assert (
        no_adapter.check(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1).reason_code
        == "unknown_resource"
    )
    inactive = service(FakeRepository(active=False), user_adapter())
    assert (
        inactive.check(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1).reason_code
        == "inactive_principal"
    )
    with pytest.raises(AuthorizationError) as error:
        inactive.require(None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1)
    assert error.value.code is DenialCode.INACTIVE_PRINCIPAL


def test_resolved_resource_still_requires_stable_id_and_authoritative_scope():
    def adapter_for(context):
        return ResourceAdapter(
            "user",
            lambda _db, _resource_id: ResourceTarget(object(), context),
            lambda _db, _principal, _action, _grants, query: query,
        )

    missing_id = ResourceContextDTO("user", None, LAB_SCOPE)
    decision = service(FakeRepository(), adapter_for(missing_id)).check(
        None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1
    )
    assert decision.reason_code == DenialCode.UNRESOLVED_RESOURCE.value

    missing_scope = ResourceContextDTO("user", 1, None)
    decision = service(FakeRepository(), adapter_for(missing_scope)).check(
        None, principal(), Action.ACCOUNT_PROFILE_VIEW, 1
    )
    assert decision.reason_code == DenialCode.MISSING_SCOPE.value


def test_fact_provider_cannot_replace_authoritative_principal_or_resource():
    adapter = upload_adapter()

    def forged(_db, _principal, _action, _target, base):
        return replace(base, principal=PrincipalDTO(999, True, True))

    adapter = replace(adapter, facts_provider=forged)
    grant = GrantRecord(7, 1, Role.FILE_UPLOADER, LAB_SCOPE, True)
    decision = service(FakeRepository(grants=(grant,)), adapter).check(
        None, principal(), Action.UPLOAD_CREATE, 10
    )
    assert not decision.allowed
    assert decision.reason_code == DenialCode.INVALID_FACTS.value


def test_resolver_state_cannot_forge_exact_or_self_identity_facts():
    def resolve(_db, resource_id):
        return ResourceTarget(
            {"id": resource_id},
            ResourceContextDTO(
                "user",
                resource_id,
                LAB_SCOPE,
                state={"exact_resource": False, "self_identity": True},
            ),
        )

    adapter = ResourceAdapter(
        "user", resolve, lambda _db, _principal, _action, _grants, query: query
    )
    decision = service(FakeRepository(), adapter).check(
        None, principal(), Action.ACCOUNT_PROFILE_VIEW, 2
    )
    assert not decision.allowed


def test_filter_query_denies_actions_needing_row_specific_relationships():
    grant = GrantRecord(7, 1, Role.FILE_UPLOADER, LAB_SCOPE, True)
    adapter = upload_adapter()
    authz = service(FakeRepository(grants=(grant,)), adapter)
    query = object()
    with pytest.raises(AuthorizationError) as unsupported:
        filter_query(
            None,
            principal(),
            Action.UPLOAD_CREATE,
            adapter,
            query,
            decision_service=authz,
        )
    assert unsupported.value.code is DenialCode.UNSUPPORTED_QUERY

    # A mismatched resource family is rejected before query support is considered.
    with pytest.raises(AuthorizationError) as error:
        filter_query(
            None,
            principal(),
            Action.ACCOUNT_PROFILE_VIEW,
            adapter,
            query,
            decision_service=authz,
        )
    assert error.value.code is DenialCode.UNKNOWN_RESOURCE


def test_admin_user_list_does_not_fall_back_to_the_callers_own_row():
    authz = service(FakeRepository(), USER_ADAPTER)
    scoped = filter_query(
        None,
        principal(),
        Action.ADMIN_USERS_VIEW,
        USER_ADAPTER,
        select(User),
        decision_service=authz,
    )
    assert "WHERE false" in str(scoped)


def test_choice_provider_receives_reloaded_principal_and_scoped_grants():
    grant = GrantRecord(7, 1, Role.FILE_UPLOADER, LAB_SCOPE, True)
    authz = service(FakeRepository(grants=(grant,)), user_adapter())
    choices = ChoiceRegistry()

    def provider(_db, current, action, grants, filters):
        assert current.user_id == 1
        assert action is Action.AUTHORIZATION_ME_WORKSPACES_VIEW
        assert grants == (grant,)
        assert filters == {"kind": "usable"}
        return ChoiceListDTO(action.value, ())

    choices.register("workspaces", Action.AUTHORIZATION_ME_WORKSPACES_VIEW, provider)
    result = list_choices(
        None,
        principal(),
        Action.AUTHORIZATION_ME_WORKSPACES_VIEW,
        "workspaces",
        {"kind": "usable"},
        choices=choices,
        decision_service=authz,
    )
    assert result.options == ()

    with pytest.raises(AuthorizationError) as confused:
        list_choices(
            None,
            principal(),
            Action.DASHBOARD_VIEW,
            "workspaces",
            choices=choices,
            decision_service=authz,
        )
    assert confused.value.code is DenialCode.NOT_AUTHORIZED

    inactive = service(FakeRepository(active=False, grants=(grant,)), user_adapter())
    with pytest.raises(AuthorizationError) as error:
        list_choices(
            None,
            principal(),
            Action.AUTHORIZATION_ME_WORKSPACES_VIEW,
            "workspaces",
            choices=choices,
            decision_service=inactive,
        )
    assert error.value.code is DenialCode.INACTIVE_PRINCIPAL
