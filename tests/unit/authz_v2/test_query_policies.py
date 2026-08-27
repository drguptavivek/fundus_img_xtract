import pytest

from authz_v2.core.actions import Action
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.resources.registry import ResourceAdapter, ResourceRegistry
from authz_v2.services.listing import filter_query


class DecisionService:
    def __init__(self, resources):
        self.resources = resources

    def active_grants(self, _principal, *, db=None):
        return ()


def test_action_specific_query_policy_precedes_scope_only_fallback():
    registry = ResourceRegistry()
    adapter = ResourceAdapter(
        "upload_target",
        lambda _db, _resource: None,
        lambda _db, _principal, _action, _grants, query: query + ("scope",),
    )
    registry.register(adapter)
    registry.register_query_policy(
        Action.UPLOAD_CREATE,
        "upload_target",
        lambda _db, _principal, _action, _grants, query: query + ("relationship",),
    )
    assert filter_query(
        None,
        object(),
        Action.UPLOAD_CREATE,
        adapter,
        (),
        decision_service=DecisionService(registry),
    ) == ("relationship",)


def test_unregistered_relationship_aware_query_denies_closed():
    registry = ResourceRegistry()
    adapter = ResourceAdapter(
        "upload_target",
        lambda _db, _resource: None,
        lambda _db, _principal, _action, _grants, query: query,
    )
    registry.register(adapter)
    with pytest.raises(AuthorizationError) as error:
        filter_query(
            None,
            object(),
            Action.UPLOAD_CREATE,
            adapter,
            (),
            decision_service=DecisionService(registry),
        )
    assert error.value.code is DenialCode.UNSUPPORTED_QUERY
