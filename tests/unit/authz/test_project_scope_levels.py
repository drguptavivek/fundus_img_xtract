"""Grant scope must match the breadth of an action's effect.

Two shapes of project action:

* **Filter** actions are confined to the rows they touch, so any grant
  covering those rows qualifies and a narrower grant simply reaches fewer
  rows. Browsing and uploads work this way.
* **Gate** actions span the project, so partial authority confers nothing
  and only a project-wide grant qualifies. Dataset curation, access and
  uploader management, WAI runs and the project overview work this way.

A grant broader than the minimum always qualifies, so a project-wide
grantee can do everything a lab-scoped one can.
"""

import pytest

from authz import ResourceRef, authorize
from authz.policies import POLICIES, HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE
from authz.types import AuthzActor, GrantSource, RelationshipGrant

PROJECT_ID, HOSPITAL_ID, LAB_ID, OTHER_LAB = 5, 1, 10, 11

GATE_ACTIONS = [
    "project.view",
    "project.access.manage",
    "project.uploaders.manage",
    "project.wai.run",
    "project.wai.results",
    "dataset.curation.view",
    "dataset.curation.update",
    "dataset.finalize",
    "dataset.delete",
    "dataset.export.create",
    "dataset.export.download",
    "dataset.share.manage",
]

FILTER_ACTIONS = [
    "project.encountersets.browse",
    "project.encountersets.browse_pii",
    "project.upload.direct_image",
    "project.upload.pregraded",
    "project.upload.remidio",
    "project.upload.encounter_set",
    "project.upload.remidio_api_sync",
]


def _grant(role, *, hospital_id=None, lab_unit_id=None):
    return RelationshipGrant(
        source=GrantSource.PROJECT_ROLE,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
        attributes={
            "project_id": PROJECT_ID,
            "hospital_id": hospital_id,
            "lab_unit_id": lab_unit_id,
            "role_names": frozenset({role}),
        },
    )


def _row(lab_unit_id=LAB_ID):
    return ResourceRef(type="row", id=1, attributes={
        "project_id": PROJECT_ID, "hospital_id": HOSPITAL_ID, "lab_unit_id": lab_unit_id})


def _actor(*roles):
    return AuthzActor(id=1, roles=frozenset(roles), hospital_id=HOSPITAL_ID)


def _role_for(action):
    """Any role the action's project branch accepts."""
    return sorted(POLICIES[action].roles_for_project())[0]


def _allowed(action, grant):
    role = _role_for(action)
    return authorize(_actor(role), action, _row(), grants=[grant]).allowed


# --- the declared classification --------------------------------------------


@pytest.mark.parametrize("action", GATE_ACTIONS)
def test_gate_actions_require_a_project_wide_grant(action):
    assert POLICIES[action].min_project_scope == PROJECT_SCOPE


@pytest.mark.parametrize("action", FILTER_ACTIONS)
def test_filter_actions_accept_the_narrowest_grant(action):
    assert POLICIES[action].min_project_scope == LAB_UNIT_SCOPE


# --- gate behaviour ----------------------------------------------------------


@pytest.mark.parametrize("action", GATE_ACTIONS)
def test_gate_action_refuses_a_lab_scoped_grant(action):
    assert not _allowed(action, _grant(_role_for(action), lab_unit_id=LAB_ID))


@pytest.mark.parametrize("action", GATE_ACTIONS)
def test_gate_action_refuses_a_hospital_scoped_grant(action):
    assert not _allowed(action, _grant(_role_for(action), hospital_id=HOSPITAL_ID))


@pytest.mark.parametrize("action", GATE_ACTIONS)
def test_gate_action_accepts_a_project_wide_grant(action):
    assert _allowed(action, _grant(_role_for(action)))


# --- filter behaviour --------------------------------------------------------


@pytest.mark.parametrize("action", FILTER_ACTIONS)
def test_filter_action_accepts_a_lab_grant_for_that_lab(action):
    assert _allowed(action, _grant(_role_for(action), lab_unit_id=LAB_ID))


@pytest.mark.parametrize("action", FILTER_ACTIONS)
def test_filter_action_still_confines_a_lab_grant_to_its_own_lab(action):
    """Scope filters rows; it does not open the whole project."""
    role = _role_for(action)
    decision = authorize(
        _actor(role), action, _row(lab_unit_id=OTHER_LAB),
        grants=[_grant(role, lab_unit_id=LAB_ID)],
    )
    assert not decision.allowed


@pytest.mark.parametrize("action", FILTER_ACTIONS)
def test_filter_action_accepts_a_project_wide_grant_too(action):
    """A broader grant always satisfies a narrower minimum."""
    assert _allowed(action, _grant(_role_for(action)))


# --- ordering ----------------------------------------------------------------


def test_scope_ordering_is_lab_then_hospital_then_project():
    policy = POLICIES["project.encountersets.browse"]
    for hospital_id, lab_unit_id in ((None, LAB_ID), (HOSPITAL_ID, None), (None, None)):
        assert policy.accepts_project_scope(hospital_id=hospital_id, lab_unit_id=lab_unit_id)

    gate = POLICIES["dataset.curation.view"]
    assert not gate.accepts_project_scope(hospital_id=None, lab_unit_id=LAB_ID)
    assert not gate.accepts_project_scope(hospital_id=HOSPITAL_ID, lab_unit_id=None)
    assert gate.accepts_project_scope(hospital_id=None, lab_unit_id=None)


def test_hospital_minimum_sits_between_the_two():
    """The middle tier exists for site-level governance (site_pi)."""
    from authz.policies import ActionPolicy

    policy = ActionPolicy(
        roles=frozenset({"site_pi"}),
        grant_sources=frozenset({GrantSource.PROJECT_ROLE}),
        min_project_scope=HOSPITAL_SCOPE,
    )
    assert not policy.accepts_project_scope(hospital_id=None, lab_unit_id=LAB_ID)
    assert policy.accepts_project_scope(hospital_id=HOSPITAL_ID, lab_unit_id=None)
    assert policy.accepts_project_scope(hospital_id=None, lab_unit_id=None)


# --- grading is governed by allocation, not by project role grants -----------


def test_no_grading_action_consults_project_role_grants():
    """Project tasks are governed by ProjectGraderAllocation alone."""
    offenders = sorted(
        action for action, policy in POLICIES.items()
        if action.startswith(("grading.", "tasks.", "intra_rater."))
        and GrantSource.PROJECT_ROLE in policy.grant_sources
    )
    assert not offenders, f"grading must not be authorized by a project role grant: {offenders}"


def test_grading_submit_is_authorized_only_by_a_slot():
    assert POLICIES["grading.resident.submit"].grant_sources == frozenset({GrantSource.GRADING_SLOT})


# --- grading: the clinician role AND an allocated slot ----------------------
# Neither half is sufficient on its own.

GRADING_ACTIONS = [
    ("grading.resident.submit", "can_grade_resident"),
    ("grading.resident2.submit", "can_grade_resident2"),
    ("grading.arbitrator.submit", "can_arbitrate"),
]
DISEASE_ID = 3


def _slot(flag, *, lab_unit_id=LAB_ID, disease_id=DISEASE_ID):
    return RelationshipGrant(
        source=GrantSource.GRADING_SLOT,
        lab_unit_id=lab_unit_id,
        attributes={
            "disease_id": disease_id,
            "can_grade_resident": flag == "can_grade_resident",
            "can_grade_resident2": flag == "can_grade_resident2",
            "can_arbitrate": flag == "can_arbitrate",
        },
    )


def _task(lab_unit_id=LAB_ID, disease_id=DISEASE_ID):
    return ResourceRef(type="grading_task", id=1, attributes={
        "project_id": None, "hospital_id": HOSPITAL_ID,
        "lab_unit_id": lab_unit_id, "disease_id": disease_id})


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_role_and_slot_together_authorize(action, flag):
    decision = authorize(_actor("ophthalmologist"), action, _task(), grants=[_slot(flag)])
    assert decision.allowed
    assert decision.grant_source is GrantSource.GRADING_SLOT


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_slot_without_a_grader_role_is_refused(action, flag):
    """An allocated slot alone does not make someone a grader."""
    assert not authorize(_actor("optometrist"), action, _task(), grants=[_slot(flag)]).allowed


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_role_without_a_slot_is_refused(action, flag):
    assert not authorize(_actor("ophthalmologist"), action, _task(), grants=[]).allowed


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_admin_is_a_grader_role_in_its_own_right(action, flag):
    """`admin` may occupy a grading slot without holding a clinical role."""
    assert authorize(_actor("admin"), action, _task(), grants=[_slot(flag)]).allowed


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_admin_still_needs_a_slot(action, flag):
    """Being a grader role does not exempt admin from holding the slot."""
    assert not authorize(_actor("admin"), action, _task(), grants=[]).allowed


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_a_non_grader_role_cannot_grade(action, flag):
    """Only ophthalmologist and admin may occupy a grading slot."""
    assert not authorize(_actor("data_manager"), action, _task(), grants=[_slot(flag)]).allowed


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_slot_for_another_lab_does_not_authorize(action, flag):
    assert not authorize(
        _actor("ophthalmologist"), action, _task(),
        grants=[_slot(flag, lab_unit_id=OTHER_LAB)],
    ).allowed


@pytest.mark.parametrize("action,flag", GRADING_ACTIONS)
def test_slot_for_another_disease_does_not_authorize(action, flag):
    assert not authorize(
        _actor("ophthalmologist"), action, _task(),
        grants=[_slot(flag, disease_id=DISEASE_ID + 1)],
    ).allowed


def test_a_resident_slot_does_not_authorize_arbitration():
    """Each slot authorizes only its own role in the workflow."""
    assert not authorize(
        _actor("ophthalmologist"), "grading.arbitrator.submit", _task(),
        grants=[_slot("can_grade_resident")],
    ).allowed


def test_every_slot_the_engine_matches_is_a_registered_action():
    """_matches_grading_slot handled resident2 and arbitrator before they existed."""
    for action, _flag in GRADING_ACTIONS:
        assert action in POLICIES, f"{action} is matched by the engine but not registered"
