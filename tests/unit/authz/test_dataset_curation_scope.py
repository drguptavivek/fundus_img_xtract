"""Dataset curation reads differently on either side of the project boundary.

The rule these tests pin:

* A row with no project keeps the classical rule - any dataset role, scoped
  by the curator's lab-unit assignments or hospital.
* A row owned by a project is open only to a project ``dataset_creator``
  holding a **project-wide** grant, and only within that project. A grant
  covering one lab of the project does not confer authority over the
  project's data, and no amount of lab-unit assignment reaches it.

Engine and SQL are asserted together on every case, because a list screen
and a single-row check must never disagree about a patient image.
"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from authz import ResourceRef, authorize, scope_query
from authz.resolver import resolve_grants
from data_authorization.models import HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from models import DirectImageUpload, Hospital, LabUnit, Project, Role, User
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import ImageFactory, UserFactory

VIEW = "dataset.curation.view"
UPDATE = "dataset.curation.update"


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name); db.add(role); db.flush()
    return role


def _new_lab(db, hospital_id, prefix):
    next_id = (db.execute(select(func.max(LabUnit.id))).scalar() or 0) + 1
    lab = LabUnit(id=next_id, name=f"{prefix}_{uuid4().hex[:6]}", hospital_id=hospital_id)
    db.add(lab); db.flush()
    return lab


def _user(db, *roles, hospital=None, labs=()):
    user = User(username=f"dc_{uuid4().hex[:8]}", password_hash="x", is_active=True,
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
    lab_a = db.merge(core_test_data["lab_unit"])
    lab_b = _new_lab(db, h1.id, "dc_labb")

    proj = Project(title="dc", code=f"DC_{uuid4().hex[:6]}", active=True)
    other = Project(title="dc2", code=f"DC2_{uuid4().hex[:6]}", active=True)
    db.add_all([proj, other]); db.flush()
    db.add_all([
        ProjectLabUnit(project_id=proj.id, lab_unit_id=lab_a.id, active=True),
        ProjectLabUnit(project_id=proj.id, lab_unit_id=lab_b.id, active=True),
        ProjectLabUnit(project_id=other.id, lab_unit_id=lab_a.id, active=True),
    ])
    db.flush()

    def image(project, lab):
        row = ImageFactory.create_direct_upload(db, hospital_id=h1.id, lab_unit_id=lab.id)
        row.project_id = project.id if project else None
        return row

    rows = {
        "free_a": image(None, lab_a),      # no project, lab A
        "free_b": image(None, lab_b),      # no project, lab B
        "proj_a": image(proj, lab_a),      # project, lab A
        "proj_b": image(proj, lab_b),      # project, lab B
        "other_a": image(other, lab_a),    # a different project
    }
    db.flush()
    return dict(h1=h1, lab_a=lab_a, lab_b=lab_b, proj=proj, other=other, rows=rows)


def _visible(db, user, world, action=VIEW):
    """Ids the SQL filter returns, asserted equal to the engine's own verdict."""
    resolved = resolve_grants(db, user)
    universe = list(world["rows"].values())
    ids = [r.id for r in universe]

    sql = set(db.execute(
        scope_query(select(DirectImageUpload.id).where(DirectImageUpload.id.in_(ids)),
                    resolved, action, DirectImageUpload)
    ).scalars())

    engine = {
        r.id for r in universe
        if authorize(resolved.actor, action,
                     ResourceRef(type="image", id=r.id, attributes={
                         "project_id": r.project_id, "hospital_id": r.hospital_id,
                         "lab_unit_id": r.lab_unit_id}),
                     grants=resolved.grants).allowed
    }
    assert sql == engine, f"SQL {sorted(sql)} != engine {sorted(engine)}"
    names = {k for k, v in world["rows"].items() if v.id in sql}
    return names


# --- classical side ---------------------------------------------------------


def test_lab_curator_sees_unowned_rows_in_their_labs_only(db_session, world):
    w = world
    user = _user(db_session, "dataset_creator", hospital=w["h1"], labs=[w["lab_a"]])
    assert _visible(db_session, user, w) == {"free_a"}


def test_lab_curator_never_sees_project_rows_even_in_their_own_lab(db_session, world):
    """The core of the rule: lab assignment stops at the project boundary."""
    w = world
    user = _user(db_session, "dataset_creator", hospital=w["h1"], labs=[w["lab_a"], w["lab_b"]])
    visible = _visible(db_session, user, w)
    assert visible == {"free_a", "free_b"}
    assert not any(n.startswith("proj") or n.startswith("other") for n in visible)


def test_other_dataset_roles_keep_classical_read_access(db_session, world):
    w = world
    user = _user(db_session, "analytics_viewer", hospital=w["h1"], labs=[w["lab_a"]])
    assert _visible(db_session, user, w) == {"free_a"}


def test_analytics_viewer_cannot_update_even_unowned_rows(db_session, world):
    """curation.update is narrower than curation.view on the classical side too."""
    w = world
    user = _user(db_session, "analytics_viewer", hospital=w["h1"], labs=[w["lab_a"]])
    assert _visible(db_session, user, w, UPDATE) == set()


# --- project side -----------------------------------------------------------


def test_project_wide_dataset_creator_sees_that_projects_rows(db_session, world):
    w = world
    user = _user(db_session, "dataset_creator")
    _grant(db_session, user, w["proj"], "dataset_creator")
    assert _visible(db_session, user, w) == {"proj_a", "proj_b"}


def test_project_grant_does_not_reach_another_project(db_session, world):
    w = world
    user = _user(db_session, "dataset_creator")
    _grant(db_session, user, w["proj"], "dataset_creator")
    assert "other_a" not in _visible(db_session, user, w)


def test_lab_scoped_grant_does_not_confer_project_curation(db_session, world):
    """A grant over one lab of the project is not authority over the project."""
    w = world
    user = _user(db_session, "dataset_creator")
    _grant(db_session, user, w["proj"], "dataset_creator", scope=LAB_UNIT_SCOPE, lab=w["lab_a"])
    assert _visible(db_session, user, w) == set()


def test_hospital_scoped_grant_does_not_confer_project_curation(db_session, world):
    w = world
    user = _user(db_session, "dataset_creator")
    _grant(db_session, user, w["proj"], "dataset_creator", scope=HOSPITAL_SCOPE, hospital=w["h1"])
    assert _visible(db_session, user, w) == set()


def test_project_wide_grant_of_another_role_does_not_confer_curation(db_session, world):
    """Only dataset_creator curates project data, whatever else the project granted."""
    w = world
    user = _user(db_session, "dataset_creator")
    _grant(db_session, user, w["proj"], "analytics_viewer")
    assert _visible(db_session, user, w) == set()


def test_project_curator_also_keeps_their_classical_labs(db_session, world):
    """The two branches are a union, not a replacement."""
    w = world
    user = _user(db_session, "dataset_creator", hospital=w["h1"], labs=[w["lab_a"]])
    _grant(db_session, user, w["proj"], "dataset_creator")
    assert _visible(db_session, user, w) == {"free_a", "proj_a", "proj_b"}


def test_project_curator_can_update_their_project_rows(db_session, world):
    w = world
    user = _user(db_session, "dataset_creator")
    _grant(db_session, user, w["proj"], "dataset_creator")
    assert _visible(db_session, user, w, UPDATE) == {"proj_a", "proj_b"}


# --- admin ------------------------------------------------------------------


def test_admin_still_sees_everything(db_session, world):
    admin = UserFactory.create_admin(db_session, username=f"dc_admin_{uuid4().hex[:6]}")
    assert _visible(db_session, admin, world) == set(world["rows"])
