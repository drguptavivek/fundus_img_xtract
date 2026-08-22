"""Lab and hospital pickers answer "where may I work", not "what may I see".

LabUnit and Hospital carry no project_id, so the resource predicate cannot
scope them. These tests pin the separate rule: a picker offers the union of
the actor's classical assignments and the labs configured on projects they
hold a qualifying grant for, always intersected with project configuration.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from authz.predicates import (
    reachable_hospital_ids,
    reachable_lab_unit_ids,
    scope_hospitals,
    scope_lab_units,
)
from authz.resolver import resolve_grants
from data_authorization.models import HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from models import Hospital, LabUnit, Project, Role, User
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import UserFactory

ACTION = "media.image.view"


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role); db.flush()
    return role


def _user(db, *roles, hospital=None, labs=()):
    user = User(username=f"pk_{uuid4().hex[:8]}", password_hash="x", is_active=True,
                hospital_id=hospital.id if hospital else None)
    user.roles = [_role(db, r) for r in roles]
    user.lab_units = list(labs)
    db.add(user); db.flush()
    return user


def _grant(db, user, project, role, *, scope=PROJECT_SCOPE, lab=None, hospital=None):
    db.add(ProjectRoleGrant(
        project_id=project.id, user_id=user.id, role_id=_role(db, role).id,
        scope_type=scope, lab_unit_id=lab.id if lab else None,
        hospital_id=hospital.id if hospital else None, active=True))
    db.flush()


@pytest.fixture
def world(db_session, core_test_data):
    db = db_session
    h1 = db.merge(core_test_data["hospital"])
    h2 = Hospital(name=f"pk_h2_{uuid4().hex[:6]}")
    db.add(h2); db.flush()
    l1a = db.merge(core_test_data["lab_unit"])
    l1b = LabUnit(name=f"pk_l1b_{uuid4().hex[:6]}", hospital_id=h1.id)
    l2a = LabUnit(name=f"pk_l2a_{uuid4().hex[:6]}", hospital_id=h2.id)
    unconfigured = LabUnit(name=f"pk_unconf_{uuid4().hex[:6]}", hospital_id=h1.id)
    db.add_all([l1b, l2a, unconfigured]); db.flush()

    proj = Project(title="pk", code=f"PK_{uuid4().hex[:6]}", active=True)
    db.add(proj); db.flush()
    # l1a and l2a are configured on the project; unconfigured deliberately is not.
    db.add_all([
        ProjectLabUnit(project_id=proj.id, lab_unit_id=l1a.id, active=True),
        ProjectLabUnit(project_id=proj.id, lab_unit_id=l2a.id, active=True),
    ])
    db.flush()
    return dict(h1=h1, h2=h2, l1a=l1a, l1b=l1b, l2a=l2a, unconfigured=unconfigured, proj=proj)


def test_no_relationships_reaches_no_labs(db_session, world):
    user = _user(db_session, "ophthalmologist")
    assert reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION) == frozenset()


def test_lab_assignment_reaches_exactly_those_labs(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist", hospital=w["h1"], labs=[w["l1a"], w["l1b"]])
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert got == {w["l1a"].id, w["l1b"].id}


def test_local_admin_hospital_scope_reaches_every_lab_in_that_hospital(db_session, world):
    w = world
    user = _user(db_session, "local_admin", hospital=w["h1"])
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert {w["l1a"].id, w["l1b"].id, w["unconfigured"].id} <= got
    assert w["l2a"].id not in got, "hospital scope must not cross hospitals"


def test_admin_is_unrestricted(db_session, world):
    admin = UserFactory.create_admin(db_session, username=f"pk_admin_{uuid4().hex[:6]}")
    assert reachable_lab_unit_ids(db_session, resolve_grants(db_session, admin), ACTION) is None


def test_project_grant_reaches_configured_labs_without_any_lab_assignment(db_session, world):
    """A pure project member has no lab_units row, yet must still see project labs."""
    w = world
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, w["proj"], "ophthalmologist")
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert got == {w["l1a"].id, w["l2a"].id}


def test_project_grant_never_reaches_an_unconfigured_lab(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, w["proj"], "ophthalmologist")
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert w["unconfigured"].id not in got


def test_lab_scoped_project_grant_reaches_only_that_lab(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, w["proj"], "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=w["l2a"])
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert got == {w["l2a"].id}


def test_hospital_scoped_project_grant_reaches_configured_labs_in_that_hospital(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, w["proj"], "ophthalmologist", scope=HOSPITAL_SCOPE, hospital=w["h1"])
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert got == {w["l1a"].id}, "configured labs of that hospital only"


def test_classical_and_project_reach_is_a_union(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist", hospital=w["h1"], labs=[w["l1b"]])
    _grant(db_session, user, w["proj"], "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=w["l2a"])
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), ACTION)
    assert got == {w["l1b"].id, w["l2a"].id}


def test_role_that_the_policy_does_not_accept_reaches_nothing(db_session, world):
    """upload.direct.create accepts only fileUploader via an upload profile."""
    w = world
    user = _user(db_session, "ophthalmologist", hospital=w["h1"], labs=[w["l1a"]])
    got = reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), "upload.direct.create")
    assert got == frozenset()


def test_unknown_action_reaches_nothing(db_session, world):
    user = _user(db_session, "ophthalmologist", labs=[world["l1a"]])
    assert reachable_lab_unit_ids(db_session, resolve_grants(db_session, user), "no.such") == frozenset()


# --- query helpers ----------------------------------------------------------


def test_scope_lab_units_filters_the_query(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist", hospital=w["h1"], labs=[w["l1a"]])
    resolved = resolve_grants(db_session, user)
    ids = set(db_session.execute(
        scope_lab_units(select(LabUnit.id), db_session, resolved, ACTION)
    ).scalars())
    assert ids == {w["l1a"].id}


def test_scope_lab_units_returns_nothing_for_an_unrelated_user(db_session, world):
    user = _user(db_session, "ophthalmologist")
    resolved = resolve_grants(db_session, user)
    ids = db_session.execute(
        scope_lab_units(select(LabUnit.id), db_session, resolved, ACTION)
    ).scalars().all()
    assert ids == []


def test_scope_lab_units_leaves_admin_queries_untouched(db_session, world):
    admin = UserFactory.create_admin(db_session, username=f"pk_admin2_{uuid4().hex[:6]}")
    resolved = resolve_grants(db_session, admin)
    scoped = set(db_session.execute(
        scope_lab_units(select(LabUnit.id), db_session, resolved, ACTION)
    ).scalars())
    every = set(db_session.execute(select(LabUnit.id)).scalars())
    assert scoped == every


def test_hospitals_follow_the_reachable_labs(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, w["proj"], "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=w["l2a"])
    resolved = resolve_grants(db_session, user)
    assert reachable_hospital_ids(db_session, resolved, ACTION) == {w["h2"].id}
    ids = set(db_session.execute(
        scope_hospitals(select(Hospital.id), db_session, resolved, ACTION)
    ).scalars())
    assert ids == {w["h2"].id}
