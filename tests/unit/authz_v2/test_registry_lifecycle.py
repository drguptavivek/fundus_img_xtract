from concurrent.futures import ThreadPoolExecutor

import pytest

from authz_v2.core.actions import Action
from authz_v2.resources.registry import ResourceAdapter, ResourceRegistry


def _adapter(resource_type="probe"):
    return ResourceAdapter(
        resource_type,
        lambda _db, _value: None,
        lambda _db, _principal, _action, _grants, query: query,
    )


def test_registry_registration_is_idempotent_only_for_the_same_adapter():
    registry = ResourceRegistry()
    adapter = _adapter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _item: registry.register(adapter), range(20)))
    assert registry.require("probe") is adapter
    with pytest.raises(ValueError, match="conflicting"):
        registry.register(_adapter())


def test_frozen_registry_rejects_all_mutation_and_retains_query_policy():
    registry = ResourceRegistry()
    adapter = _adapter()
    policy = lambda _db, _principal, _action, _grants, query: query
    registry.register(adapter)
    registry.register_query_policy(Action.ACCOUNT_PROFILE_VIEW, "probe", policy)
    registry.freeze()
    assert registry.query_policy(Action.ACCOUNT_PROFILE_VIEW, "probe") is policy
    with pytest.raises(RuntimeError, match="frozen"):
        registry.register(_adapter("other"))
    with pytest.raises(RuntimeError, match="frozen"):
        registry.replace(adapter)
