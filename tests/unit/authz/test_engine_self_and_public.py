"""Engine support for deliberately public actions and self-owned records."""

import pytest

from authz.adapters import self_grant
from authz.engine import authorize
from authz.types import AuthzActor, GrantSource, ResourceRef


ANON = AuthzActor(id=0, roles=frozenset())
USER = AuthzActor(id=7, roles=frozenset({"resident"}))


@pytest.mark.parametrize("action", ["auth.login", "help.view", "public.view", "docs.api.view"])
def test_public_actions_allow_without_roles_or_grants(action: str) -> None:
    decision = authorize(ANON, action)
    assert decision.allowed
    assert decision.grant_source is GrantSource.PUBLIC


def test_self_action_allows_the_owner() -> None:
    decision = authorize(
        USER,
        "account.profile.update",
        ResourceRef(type="user", id=7),
        grants=[self_grant(7)],
    )
    assert decision.allowed
    assert decision.grant_source is GrantSource.SELF


def test_self_action_denies_another_users_record() -> None:
    decision = authorize(
        USER,
        "account.profile.update",
        ResourceRef(type="user", id=8),
        grants=[self_grant(7)],
    )
    assert not decision.allowed


def test_self_action_denies_without_the_self_grant() -> None:
    decision = authorize(USER, "account.profile.update", ResourceRef(type="user", id=7))
    assert not decision.allowed


def test_self_action_without_a_named_resource_is_implicitly_the_actor() -> None:
    """Actions with requires_resource=false read the actor's own record."""
    decision = authorize(USER, "account.profile.view", grants=[self_grant(7)])
    assert decision.allowed


def test_password_change_is_not_reachable_by_role_alone() -> None:
    """An admin role must not, by itself, satisfy a self-scoped action."""
    admin = AuthzActor(id=1, roles=frozenset({"admin"}))
    decision = authorize(admin, "account.password.change", ResourceRef(type="user", id=7))
    assert not decision.allowed
