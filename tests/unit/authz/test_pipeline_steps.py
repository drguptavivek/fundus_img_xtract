"""The three steps of the pipeline reach data by three different routes.

Upload, verification and grading are separate stages, and holding one
confers nothing at the next. Each is scoped differently:

    upload        own lab units, or the (project, lab unit) pairs the
                  uploader's upload assignments cover
    verification  own lab units, or a verification role held through an
                  explicit project role grant
    grading       a grading slot for that disease and lab unit, plus a
                  project allocation when the task belongs to a project

Within a lab unit an uploader sees every upload, not only their own; "mine"
is a filter on that list, not the boundary of it.
"""

import pytest

from authz import ResourceRef, authorize
from authz.policies import POLICIES
from authz.types import AuthzActor, GrantSource, RelationshipGrant

HOSPITAL, MY_LAB, OTHER_LAB = 1, 10, 11
MY_PROJECT, OTHER_PROJECT = 5, 6

UPLOAD_VIEW = "upload.direct.view"
VERIFY = "verification.encounter_set.update"
GRADE = "grading.resident.submit"


def _actor(*roles):
    return AuthzActor(id=1, roles=frozenset(roles), hospital_id=HOSPITAL)


def _lab_grant(lab=MY_LAB):
    return RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=lab)


def _upload_assignment(project=MY_PROJECT, lab=MY_LAB):
    """What an upload profile assignment conveys: a project and a lab unit."""
    return RelationshipGrant(
        source=GrantSource.UPLOAD_PROFILE,
        lab_unit_id=lab,
        attributes={"project_id": project, "lab_unit_id": lab, "hospital_id": None},
    )


def _res(project_id=None, lab=MY_LAB, **extra):
    attrs = {"project_id": project_id, "hospital_id": HOSPITAL, "lab_unit_id": lab}
    attrs.update(extra)
    return ResourceRef(type="upload", id=1, attributes=attrs)


# --- step one: upload --------------------------------------------------------


def test_uploader_sees_non_project_uploads_in_their_own_lab():
    actor, grants = _actor("fileUploader"), [_lab_grant()]
    assert authorize(actor, UPLOAD_VIEW, _res(), grants=grants).allowed


def test_uploader_does_not_see_another_lab():
    actor, grants = _actor("fileUploader"), [_lab_grant()]
    assert not authorize(actor, UPLOAD_VIEW, _res(lab=OTHER_LAB), grants=grants).allowed


def test_uploader_sees_project_uploads_in_an_assigned_lab():
    """Not only their own uploads: everything in that lab unit."""
    actor = _actor("fileUploader")
    grants = [_lab_grant(), _upload_assignment()]
    assert authorize(actor, UPLOAD_VIEW, _res(project_id=MY_PROJECT), grants=grants).allowed


def test_uploader_does_not_see_a_project_they_have_no_assignment_for():
    actor = _actor("fileUploader")
    grants = [_lab_grant(), _upload_assignment()]
    assert not authorize(actor, UPLOAD_VIEW, _res(project_id=OTHER_PROJECT), grants=grants).allowed


def test_uploader_does_not_see_another_lab_of_an_assigned_project():
    actor = _actor("fileUploader")
    grants = [_lab_grant(), _upload_assignment()]
    decision = authorize(actor, UPLOAD_VIEW, _res(project_id=MY_PROJECT, lab=OTHER_LAB), grants=grants)
    assert not decision.allowed


def test_lab_assignment_alone_does_not_reach_a_project_upload():
    """The classical branch stops at the project boundary, as everywhere else."""
    actor, grants = _actor("fileUploader"), [_lab_grant()]
    assert not authorize(actor, UPLOAD_VIEW, _res(project_id=MY_PROJECT), grants=grants).allowed


def test_an_assignment_carrying_clinical_limits_still_enforces_them():
    """A full upload profile constrains what may be created, not just where."""
    actor = _actor("fileUploader")
    grant = RelationshipGrant(
        source=GrantSource.UPLOAD_PROFILE,
        lab_unit_id=MY_LAB,
        attributes={"project_id": MY_PROJECT, "lab_unit_id": MY_LAB,
                    "disease_ids": frozenset({1})},
    )
    allowed = authorize(actor, UPLOAD_VIEW, _res(project_id=MY_PROJECT, disease_id=1), grants=[grant])
    refused = authorize(actor, UPLOAD_VIEW, _res(project_id=MY_PROJECT, disease_id=2), grants=[grant])
    assert allowed.allowed and not refused.allowed


# --- the steps do not leak into one another ---------------------------------


def test_an_upload_assignment_does_not_confer_verification():
    """Uploaders are not verifiers."""
    actor = _actor("fileUploader")
    grants = [_lab_grant(), _upload_assignment()]
    assert not authorize(actor, VERIFY, _res(project_id=MY_PROJECT), grants=grants).allowed


def test_an_upload_assignment_does_not_confer_grading():
    actor = _actor("fileUploader", "ophthalmologist")
    grants = [_lab_grant(), _upload_assignment()]
    task = _res(project_id=MY_PROJECT, disease_id=3)
    assert not authorize(actor, GRADE, task, grants=grants).allowed


def test_a_grading_slot_does_not_confer_upload_visibility():
    actor = _actor("ophthalmologist")
    slot = RelationshipGrant(
        source=GrantSource.GRADING_SLOT, lab_unit_id=MY_LAB,
        attributes={"disease_id": 3, "can_grade_resident": True},
    )
    assert not authorize(actor, UPLOAD_VIEW, _res(), grants=[slot]).allowed


# --- the grant sources stay distinct per step -------------------------------


def test_each_step_accepts_only_its_own_relationship():
    upload = POLICIES[UPLOAD_VIEW].grant_sources
    verify = POLICIES[VERIFY].grant_sources
    grade = POLICIES[GRADE].grant_sources

    assert GrantSource.UPLOAD_PROFILE in upload
    assert GrantSource.UPLOAD_PROFILE not in verify
    assert GrantSource.UPLOAD_PROFILE not in grade
    assert grade == frozenset({GrantSource.GRADING_SLOT})
