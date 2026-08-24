"""WAI inference reach follows lab-unit allocation, including upload profiles.

The rule these pin:

* Reading inference output and triggering a run are both scoped by lab unit,
  on both sides of the project boundary. A lab-scoped project grant reaches
  that lab and no more; it is a filter, not a project-wide gate.
* An upload profile assignment carries the same reach. This is the load-bearing
  case: an automated Remidio API pull is created by a schedule and records no
  uploading user, so field staff reach the inferences run on those pulls
  through the lab units their profiles cover, never through ownership.
* Because the reach is the *lab unit* and not the profile, a project running a
  manual profile alongside an automated one still resolves: an assignment to
  either profile in lab L reaches everything in lab L.
"""

from uuid import uuid4

import pytest

from authz import ResourceRef, authorize
from authz.policies import POLICIES
from authz.types import AuthzActor, GrantSource, RelationshipGrant

PROJECT_ID, HOSPITAL_ID, LAB_A, LAB_B = 7, 1, 20, 21
READ = "inference.wai.rows"
RUN = "inference.wai.run"


def _actor(*roles):
    return AuthzActor(id=1, roles=frozenset(roles), hospital_id=HOSPITAL_ID)


def _row(*, project_id=PROJECT_ID, lab_unit_id=LAB_A):
    return ResourceRef(type="inference_run", id=1, attributes={
        "project_id": project_id, "hospital_id": HOSPITAL_ID, "lab_unit_id": lab_unit_id})


def _project_grant(role, *, lab_unit_id=None):
    return RelationshipGrant(
        source=GrantSource.PROJECT_ROLE,
        lab_unit_id=lab_unit_id,
        attributes={
            "project_id": PROJECT_ID, "hospital_id": None,
            "lab_unit_id": lab_unit_id, "role_names": frozenset({role}),
        },
    )


def _upload_assignment(*, lab_unit_id=LAB_A):
    """What the resolver emits for a ProjectUploadProfileAssignment.

    Note what it does not carry: the profile's identity. Reach is the
    (project, lab unit) pair, which is why a manual-profile assignment also
    reaches rows the automated profile ingested in the same lab.
    """
    return RelationshipGrant(
        source=GrantSource.UPLOAD_PROFILE,
        lab_unit_id=lab_unit_id,
        attributes={"project_id": PROJECT_ID, "lab_unit_id": lab_unit_id, "hospital_id": None},
    )


def _lab_assignment(lab_unit_id=LAB_A):
    return RelationshipGrant(
        source=GrantSource.LAB_UNIT_ASSIGNMENT,
        lab_unit_id=lab_unit_id,
        attributes={"lab_unit_id": lab_unit_id},
    )


# --- the actions exist and are filters, not gates ---------------------------


@pytest.mark.parametrize("action", [READ, RUN, "inference.wai.summary", "inference.wai.retry"])
def test_action_is_registered(action):
    assert action in POLICIES


@pytest.mark.parametrize("action", ["project.wai.run", "project.wai.results"])
def test_project_wai_is_lab_scoped_not_a_project_wide_gate(action):
    from authz.policies import LAB_UNIT_SCOPE

    assert POLICIES[action].min_project_scope == LAB_UNIT_SCOPE


# --- upload profile assignments carry inference reach -----------------------


def test_field_role_reaches_project_inference_through_an_upload_assignment():
    """The automated-pull case: no owner exists, so the profile's lab carries it."""
    decision = authorize(
        _actor("field_optometrist"), READ, _row(), grants=[_upload_assignment()]
    )
    assert decision.allowed


def test_that_reach_does_not_extend_to_another_lab_of_the_same_project():
    assert not authorize(
        _actor("field_optometrist"), READ, _row(lab_unit_id=LAB_B),
        grants=[_upload_assignment(lab_unit_id=LAB_A)],
    ).allowed


def test_a_single_assignment_reaches_every_profile_in_that_lab():
    """Manual and automated profiles in one lab resolve to the same reach.

    The grant names (project, lab), so a row ingested by the automated profile
    is reached by an assignment made against the manual one. This is asserted
    directly because it is the case the requirement turns on.
    """
    manual_assignment = _upload_assignment(lab_unit_id=LAB_A)
    row_from_automated_profile = _row(lab_unit_id=LAB_A)
    assert authorize(
        _actor("field_optometrist"), READ, row_from_automated_profile,
        grants=[manual_assignment],
    ).allowed


def test_field_role_may_request_a_run_within_that_lab():
    assert authorize(
        _actor("field_optometrist"), RUN, _row(), grants=[_upload_assignment()]
    ).allowed


def test_no_relationship_reaches_nothing():
    assert not authorize(_actor("field_optometrist"), READ, _row(), grants=[]).allowed


# --- lab-scoped project grants are enough -----------------------------------


def test_lab_scoped_verifier_grant_reaches_that_labs_inference():
    assert authorize(
        _actor("verifier"), READ, _row(), grants=[_project_grant("verifier", lab_unit_id=LAB_A)]
    ).allowed


def test_lab_scoped_verifier_grant_stops_at_its_own_lab():
    assert not authorize(
        _actor("verifier"), READ, _row(lab_unit_id=LAB_B),
        grants=[_project_grant("verifier", lab_unit_id=LAB_A)],
    ).allowed


def test_project_wide_grant_reaches_the_project():
    assert authorize(
        _actor("verifier"), READ, _row(lab_unit_id=LAB_B), grants=[_project_grant("verifier")]
    ).allowed


# --- the project boundary still holds ---------------------------------------


def test_lab_assignment_alone_never_reaches_a_project_row():
    """Classical lab membership is not authority over project data."""
    assert not authorize(
        _actor("verifier"), READ, _row(), grants=[_lab_assignment(LAB_A)]
    ).allowed


def test_lab_assignment_does_reach_a_classical_row():
    assert authorize(
        _actor("verifier"), READ, _row(project_id=None), grants=[_lab_assignment(LAB_A)]
    ).allowed


def test_classical_run_requires_the_lab_too():
    """L19: the classical branch used to test the role and nothing else."""
    assert not authorize(
        _actor("verifier"), RUN, _row(project_id=None, lab_unit_id=LAB_B),
        grants=[_lab_assignment(LAB_A)],
    ).allowed


# --- retry is narrower than reading -----------------------------------------


def test_verifier_may_read_but_not_retry():
    grants = [_lab_assignment(LAB_A)]
    row = _row(project_id=None)
    assert authorize(_actor("verifier"), READ, row, grants=grants).allowed
    assert not authorize(_actor("verifier"), "inference.wai.retry", row, grants=grants).allowed


def test_data_manager_may_retry():
    assert authorize(
        _actor("data_manager"), "inference.wai.retry", _row(project_id=None),
        grants=[_lab_assignment(LAB_A)],
    ).allowed


# --- identifiers -------------------------------------------------------------


def test_rows_may_show_identifiers_but_the_aggregate_need_not():
    assert POLICIES[READ].shows_pii
    assert not POLICIES["inference.wai.summary"].shows_pii
