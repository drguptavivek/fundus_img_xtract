"""Who may see and change a user record.

Creating and changing users is an admin power: `admin` exercises it
globally, `local_admin` within their own hospital. `data_manager` may read
user allocations and activity for their hospital but never edit them.

A user record is hospital-shaped and belongs to no lab or project, so it
uses the own-hospital grant rather than lab assignment. That grant carries
no lab authority, so widening it here does not widen anything else.
"""

import pytest

from authz import ResourceRef, authorize
from authz.adapters import admin_global_grant, own_hospital_grant
from authz.policies import POLICIES
from authz.types import AuthzActor, GrantSource

MY_HOSPITAL, OTHER_HOSPITAL = 1, 2
VIEW, MANAGE = "admin.users.view", "admin.users.manage"


def _actor(*roles, hospital_id=MY_HOSPITAL):
    return AuthzActor(id=1, roles=frozenset(roles), hospital_id=hospital_id)


def _grants(actor):
    return [g for g in (admin_global_grant(actor), own_hospital_grant(actor)) if g]


def _user_in(hospital_id):
    return ResourceRef(type="user", id=99, attributes={
        "project_id": None, "hospital_id": hospital_id, "lab_unit_id": None})


def _allowed(actor, action, hospital_id):
    return authorize(actor, action, _user_in(hospital_id), grants=_grants(actor)).allowed


# --- admin: global -----------------------------------------------------------

@pytest.mark.parametrize("action", [VIEW, MANAGE])
@pytest.mark.parametrize("hospital", [MY_HOSPITAL, OTHER_HOSPITAL])
def test_admin_reaches_users_in_any_hospital(action, hospital):
    assert _allowed(_actor("admin"), action, hospital)


# --- local_admin: own hospital ----------------------------------------------

@pytest.mark.parametrize("action", [VIEW, MANAGE])
def test_local_admin_reaches_their_own_hospital(action):
    assert _allowed(_actor("local_admin"), action, MY_HOSPITAL)


@pytest.mark.parametrize("action", [VIEW, MANAGE])
def test_local_admin_does_not_reach_another_hospital(action):
    assert not _allowed(_actor("local_admin"), action, OTHER_HOSPITAL)


# --- data_manager: read only, own hospital ----------------------------------

def test_data_manager_may_view_their_own_hospital():
    assert _allowed(_actor("data_manager"), VIEW, MY_HOSPITAL)


def test_data_manager_may_not_manage_users():
    """The whole point of the split: viewing allocations is not editing them."""
    assert not _allowed(_actor("data_manager"), MANAGE, MY_HOSPITAL)


def test_data_manager_does_not_reach_another_hospital():
    assert not _allowed(_actor("data_manager"), VIEW, OTHER_HOSPITAL)


# --- everyone else -----------------------------------------------------------

@pytest.mark.parametrize("role", ["ophthalmologist", "discrepancy_reviewer", "fileUploader",
                                  "analytics_viewer", "dataset_creator"])
@pytest.mark.parametrize("action", [VIEW, MANAGE])
def test_other_roles_reach_no_user_records(role, action):
    assert not _allowed(_actor(role), action, MY_HOSPITAL)


def test_an_actor_with_no_hospital_reaches_nothing():
    assert not _allowed(_actor("data_manager", hospital_id=None), VIEW, MY_HOSPITAL)


# --- the grant stays narrow --------------------------------------------------

def test_own_hospital_is_accepted_only_by_the_user_actions():
    """It must not become a general hospital-wide power."""
    accepting = sorted(
        action for action, policy in POLICIES.items()
        if GrantSource.OWN_HOSPITAL in policy.grant_sources
    )
    assert accepting == [MANAGE, VIEW]


def test_own_hospital_grant_carries_no_lab_authority():
    grant = own_hospital_grant(_actor("data_manager"))
    assert grant.lab_unit_id is None
    assert grant.hospital_id == MY_HOSPITAL
