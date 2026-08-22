"""The predicate compiler must agree with the engine, row for row.

This is the safety net for the cutover. For every model and every user
archetype, the set of ids ``scope_query`` returns is compared against the
set ``authorize`` allows when asked about each row individually. Any
divergence means a list endpoint would show (or hide) rows the engine
would decide differently.
"""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from authz import ResourceRef, authorize
from authz.predicates import scope_predicate, scope_query
from authz.resolver import resolve_grants
from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from encounter_sets.models import ProjectEncounterSetPermission
from models import (
    DirectImageUpload,
    EncounterFile,
    Hospital,
    LabUnit,
    PatientEncounters,
    Project,
    Role,
    User,
)
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import ImageFactory, UserFactory

ACTION = "media.image.view"


# --- fixtures ---------------------------------------------------------------


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _user(db, *roles, hospital=None, labs=()):
    user = User(username=f"pr_{uuid4().hex[:8]}", password_hash="x", is_active=True,
                hospital_id=hospital.id if hospital else None)
    user.roles = [_role(db, r) for r in roles]
    user.lab_units = list(labs)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def world(db_session, core_test_data):
    """Two hospitals, two labs each, two projects, and images of every kind."""
    db = db_session
    h1 = db.merge(core_test_data["hospital"])
    h2 = Hospital(name=f"pr_h2_{uuid4().hex[:6]}")
    db.add(h2); db.flush()
    l1a = db.merge(core_test_data["lab_unit"])
    l1b = LabUnit(name=f"pr_l1b_{uuid4().hex[:6]}", hospital_id=h1.id)
    l2a = LabUnit(name=f"pr_l2a_{uuid4().hex[:6]}", hospital_id=h2.id)
    db.add_all([l1b, l2a]); db.flush()

    pA = Project(title="pr A", code=f"PRA_{uuid4().hex[:6]}", active=True)
    pB = Project(title="pr B", code=f"PRB_{uuid4().hex[:6]}", active=True)
    db.add_all([pA, pB]); db.flush()
    db.add_all([
        ProjectLabUnit(project_id=pA.id, lab_unit_id=l1a.id, active=True),
        ProjectLabUnit(project_id=pA.id, lab_unit_id=l2a.id, active=True),
        ProjectLabUnit(project_id=pB.id, lab_unit_id=l1b.id, active=True),
    ])
    db.flush()

    def direct(project, lab, hosp):
        row = ImageFactory.create_direct_upload(db, hospital_id=hosp.id, lab_unit_id=lab.id)
        row.project_id = project.id if project else None
        return row

    def encounter(project, lab):
        row = PatientEncounters(
            uuid=str(uuid4()), name="pr", patient_id=f"PR-{uuid4().hex[:6]}",
            capture_date="2024-01-01", capture_date_dt=date(2024, 1, 1),
            lab_unit_id=lab.id, project_id=project.id if project else None,
            encounter_verified_status="pending",
        )
        db.add(row); return row

    rows = {
        "direct": [
            direct(None, l1a, h1), direct(None, l1b, h1), direct(None, l2a, h2),
            direct(pA, l1a, h1), direct(pA, l2a, h2), direct(pB, l1b, h1),
        ],
        "encounter": [
            encounter(None, l1a), encounter(None, l2a),
            encounter(pA, l1a), encounter(pA, l2a), encounter(pB, l1b),
        ],
    }
    db.flush()
    return dict(h1=h1, h2=h2, l1a=l1a, l1b=l1b, l2a=l2a, pA=pA, pB=pB, rows=rows)


def _grant(db, user, project, role, *, scope=PROJECT_SCOPE, lab=None):
    db.add(ProjectRoleGrant(project_id=project.id, user_id=user.id, role_id=_role(db, role).id,
                            scope_type=scope, lab_unit_id=lab.id if lab else None, active=True))
    db.flush()


# --- the equivalence oracle -------------------------------------------------


def _ref(model, row) -> ResourceRef:
    if model is PatientEncounters:
        lab = row.lab_unit
        attrs = {"project_id": row.project_id, "hospital_id": lab.hospital_id if lab else None,
                 "lab_unit_id": row.lab_unit_id}
    else:
        attrs = {"project_id": row.project_id, "hospital_id": row.hospital_id,
                 "lab_unit_id": row.lab_unit_id}
    return ResourceRef(type=model.__tablename__, id=row.id, attributes=attrs)


def _assert_equivalent(db, user, model, universe):
    resolved = resolve_grants(db, user)
    engine_allows = {
        r.id for r in universe
        if authorize(resolved.actor, ACTION, _ref(model, r), grants=resolved.grants).allowed
    }
    ids = [r.id for r in universe]
    sql_allows = set(db.execute(
        scope_query(select(model.id).where(model.id.in_(ids)), resolved, ACTION, model)
    ).scalars())
    assert sql_allows == engine_allows, (
        f"{model.__name__}/{sorted(r.name for r in user.roles)}: "
        f"sql={sorted(sql_allows)} engine={sorted(engine_allows)}"
    )
    return sql_allows


ARCHETYPES = [
    "no_relationships",
    "lab_member_h1",
    "local_admin_h1",
    "project_A_member",
    "project_A_lab_scoped_l1a",
    "lab_member_and_project_B",
    "admin",
]


def _make(db, world, archetype):
    w = world
    if archetype == "no_relationships":
        return _user(db, "ophthalmologist")
    if archetype == "lab_member_h1":
        return _user(db, "ophthalmologist", hospital=w["h1"], labs=[w["l1a"], w["l1b"]])
    if archetype == "local_admin_h1":
        return _user(db, "local_admin", hospital=w["h1"])
    if archetype == "project_A_member":
        u = _user(db, "ophthalmologist"); _grant(db, u, w["pA"], "ophthalmologist"); return u
    if archetype == "project_A_lab_scoped_l1a":
        u = _user(db, "ophthalmologist")
        _grant(db, u, w["pA"], "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=w["l1a"]); return u
    if archetype == "lab_member_and_project_B":
        u = _user(db, "ophthalmologist", hospital=w["h1"], labs=[w["l1a"]])
        _grant(db, u, w["pB"], "ophthalmologist"); return u
    if archetype == "admin":
        return UserFactory.create_admin(db, username=f"pr_admin_{uuid4().hex[:6]}")
    raise AssertionError(archetype)


@pytest.mark.parametrize("archetype", ARCHETYPES)
@pytest.mark.parametrize("model_key,model", [("direct", DirectImageUpload), ("encounter", PatientEncounters)])
def test_predicate_matches_engine_row_for_row(db_session, world, archetype, model_key, model):
    user = _make(db_session, world, archetype)
    _assert_equivalent(db_session, user, model, world["rows"][model_key])


# --- the specific leak, asserted directly on SQL ----------------------------


def test_lab_member_sees_only_non_project_rows_in_their_labs(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist", hospital=w["h1"], labs=[w["l1a"], w["l1b"]])
    allowed = _assert_equivalent(db_session, user, DirectImageUpload, w["rows"]["direct"])
    rows = {r.id: r for r in w["rows"]["direct"]}
    for rid in allowed:
        assert rows[rid].project_id is None, "lab membership must never reach a project row"
        assert rows[rid].lab_unit_id in {w["l1a"].id, w["l1b"].id}
    assert allowed, "sanity: the member does see their classical rows"


def test_project_member_sees_only_their_project_rows(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist"); _grant(db_session, user, w["pA"], "ophthalmologist")
    allowed = _assert_equivalent(db_session, user, DirectImageUpload, w["rows"]["direct"])
    rows = {r.id: r for r in w["rows"]["direct"]}
    assert allowed
    assert {rows[r].project_id for r in allowed} == {w["pA"].id}


def test_lab_scoped_project_grant_excludes_other_labs_of_same_project(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, w["pA"], "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=w["l1a"])
    allowed = _assert_equivalent(db_session, user, DirectImageUpload, w["rows"]["direct"])
    rows = {r.id: r for r in w["rows"]["direct"]}
    assert allowed
    assert all(rows[r].lab_unit_id == w["l1a"].id for r in allowed)


def test_legacy_capability_row_is_honoured_by_sql(db_session, world):
    w = world
    user = _user(db_session, "ophthalmologist")
    db_session.add(ProjectEncounterSetPermission(
        project_id=w["pA"].id, lab_unit_id=w["l1a"].id, user_id=user.id, active=True, can_browse=True))
    db_session.flush()
    allowed = _assert_equivalent(db_session, user, DirectImageUpload, w["rows"]["direct"])
    rows = {r.id: r for r in w["rows"]["direct"]}
    assert allowed
    assert all(rows[r].project_id == w["pA"].id and rows[r].lab_unit_id == w["l1a"].id for r in allowed)


def test_admin_sees_everything(db_session, world):
    admin = UserFactory.create_admin(db_session, username=f"pr_admin2_{uuid4().hex[:6]}")
    allowed = _assert_equivalent(db_session, admin, DirectImageUpload, world["rows"]["direct"])
    assert allowed == {r.id for r in world["rows"]["direct"]}


def test_unknown_action_selects_nothing(db_session, world):
    user = UserFactory.create_admin(db_session, username=f"pr_admin3_{uuid4().hex[:6]}")
    resolved = resolve_grants(db_session, user)
    rows = db_session.execute(
        scope_query(select(DirectImageUpload.id), resolved, "no.such.action", DirectImageUpload)
    ).scalars().all()
    assert rows == []


def test_unregistered_model_is_an_explicit_error(db_session, world):
    resolved = resolve_grants(db_session, _user(db_session, "admin"))
    with pytest.raises(LookupError, match="no registered authz scope"):
        scope_predicate(resolved, ACTION, Hospital)
