"""The grant resolver turns persisted relationships into engine grants.

These tests pin the one behaviour the whole migration rests on: the grant set
the resolver produces must make the engine reach the same decision the
existing per-module authorizers reach. Each test seeds one relationship kind
and checks both that the grant is emitted and that it authorizes correctly.
"""

from uuid import uuid4

from authz import ResourceRef, authorize
from authz.resolver import resolve_grants
from authz.types import GrantSource
from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from encounter_sets.models import ProjectEncounterSetPermission
from models import LabUnit, Project, Role, User, UserDiseaseUnitRole
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import UserFactory


def _role(db, name: str) -> Role:
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _user(db, *roles: str) -> User:
    user = User(username=f"rs_{uuid4().hex[:8]}", password_hash="x", is_active=True)
    user.roles = [_role(db, name) for name in roles]
    db.add(user)
    db.flush()
    return user


def _project(db) -> Project:
    suffix = uuid4().hex[:6].upper()
    project = Project(title=f"Resolver {suffix}", code=f"RS_{suffix}", active=True)
    db.add(project)
    db.flush()
    return project


def _configure_lab(db, project: Project, lab: LabUnit) -> None:
    db.add(ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True))
    db.flush()


def _grant(db, user: User, project: Project, role: str, *, scope=PROJECT_SCOPE, lab: LabUnit | None = None):
    db.add(ProjectRoleGrant(
        project_id=project.id,
        user_id=user.id,
        role_id=_role(db, role).id,
        scope_type=scope,
        lab_unit_id=lab.id if lab else None,
        active=True,
    ))
    db.flush()


def _image(project_id, hospital_id, lab_unit_id) -> ResourceRef:
    return ResourceRef(type="image", id=uuid4().hex, attributes={
        "project_id": project_id, "hospital_id": hospital_id, "lab_unit_id": lab_unit_id,
    })


# --- always-present grants -------------------------------------------------

def test_every_user_gets_a_self_grant(db_session):
    user = _user(db_session, "resident")
    resolved = resolve_grants(db_session, user)
    (grant,) = resolved.of(GrantSource.SELF)
    assert grant.resource_id == user.id


def test_admin_gets_admin_global_grant(db_session):
    admin = UserFactory.create_admin(db_session, username=f"rs_admin_{uuid4().hex[:6]}")
    assert resolve_grants(db_session, admin).of(GrantSource.ADMIN_GLOBAL)


def test_non_admin_gets_no_admin_global_grant(db_session):
    assert not resolve_grants(db_session, _user(db_session, "resident")).of(GrantSource.ADMIN_GLOBAL)


# --- classical scope --------------------------------------------------------

def test_lab_unit_assignment_emits_one_grant_per_lab(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    user = _user(db_session, "ophthalmologist")
    user.lab_units = [lab]
    db_session.flush()

    grants = resolve_grants(db_session, user).of(GrantSource.LAB_UNIT_ASSIGNMENT)
    assert [g.lab_unit_id for g in grants] == [lab.id]


def test_classical_scope_does_not_authorize_a_project_row(db_session, core_test_data):
    """The leak this migration closes: lab membership must not reach project rows."""
    lab = db_session.merge(core_test_data["lab_unit"])
    project = _project(db_session)
    _configure_lab(db_session, project, lab)
    user = _user(db_session, "ophthalmologist")
    user.lab_units = [lab]
    db_session.flush()

    resolved = resolve_grants(db_session, user)
    non_project = _image(None, lab.hospital_id, lab.id)
    project_row = _image(project.id, lab.hospital_id, lab.id)

    assert authorize(resolved.actor, "media.image.view", non_project, grants=resolved.grants).allowed
    assert not authorize(resolved.actor, "media.image.view", project_row, grants=resolved.grants).allowed


# --- project role grants ----------------------------------------------------

def test_project_role_grant_authorizes_only_its_project(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    mine, other = _project(db_session), _project(db_session)
    _configure_lab(db_session, mine, lab)
    _configure_lab(db_session, other, lab)
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, mine, "ophthalmologist")

    resolved = resolve_grants(db_session, user)
    assert resolved.project_ids == {mine.id}
    assert authorize(resolved.actor, "media.image.view", _image(mine.id, lab.hospital_id, lab.id), grants=resolved.grants).allowed
    assert not authorize(resolved.actor, "media.image.view", _image(other.id, lab.hospital_id, lab.id), grants=resolved.grants).allowed


def test_lab_scoped_project_grant_does_not_reach_other_labs(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    other_lab = LabUnit(name=f"rs_lab_{uuid4().hex[:6]}", hospital_id=lab.hospital_id)
    db_session.add(other_lab)
    db_session.flush()
    project = _project(db_session)
    _configure_lab(db_session, project, lab, )
    _configure_lab(db_session, project, other_lab)
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, project, "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=lab)

    resolved = resolve_grants(db_session, user)
    assert authorize(resolved.actor, "media.image.view", _image(project.id, lab.hospital_id, lab.id), grants=resolved.grants).allowed
    assert not authorize(resolved.actor, "media.image.view", _image(project.id, lab.hospital_id, other_lab.id), grants=resolved.grants).allowed


def test_grant_on_lab_no_longer_configured_on_project_is_dropped(db_session, core_test_data):
    """Mirrors the project-boundary check in project_role_names_for_scope."""
    lab = db_session.merge(core_test_data["lab_unit"])
    project = _project(db_session)  # lab deliberately NOT configured
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, project, "ophthalmologist", scope=LAB_UNIT_SCOPE, lab=lab)

    assert not resolve_grants(db_session, user).of(GrantSource.PROJECT_ROLE)


def test_inactive_project_grant_is_ignored(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    project = _project(db_session)
    _configure_lab(db_session, project, lab)
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, project, "ophthalmologist")
    db_session.query(ProjectRoleGrant).filter_by(user_id=user.id).update({"active": False})
    db_session.flush()

    assert not resolve_grants(db_session, user).of(GrantSource.PROJECT_ROLE)


def test_multiple_roles_on_one_scope_merge_into_one_grant(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    project = _project(db_session)
    _configure_lab(db_session, project, lab)
    user = _user(db_session, "ophthalmologist")
    _grant(db_session, user, project, "ophthalmologist")
    _grant(db_session, user, project, "verifier")

    (grant,) = resolve_grants(db_session, user).of(GrantSource.PROJECT_ROLE)
    assert grant.attr("role_names") == {"ophthalmologist", "verifier"}


# --- legacy capability rows -------------------------------------------------

def test_legacy_capability_row_emits_its_enabled_capabilities(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    project = _project(db_session)
    _configure_lab(db_session, project, lab)
    user = _user(db_session, "ophthalmologist")
    db_session.add(ProjectEncounterSetPermission(
        project_id=project.id, lab_unit_id=lab.id, user_id=user.id, active=True,
        can_browse=True, can_verify=True,
    ))
    db_session.flush()

    (grant,) = resolve_grants(db_session, user).of(GrantSource.LEGACY_PROJECT_CAPABILITY)
    assert grant.attr("capabilities") == {"browse", "verify"}
    assert grant.attr("project_id") == project.id
    assert grant.attr("hospital_id") == lab.hospital_id


# --- grading slots ----------------------------------------------------------

def test_grading_slots_emit_one_grant_per_active_slot(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    other_disease = db_session.merge(core_test_data["glaucoma"])
    user = _user(db_session, "resident")
    db_session.add(UserDiseaseUnitRole(user_id=user.id, disease_id=disease.id, lab_unit_id=lab.id,
                                       can_grade_resident=True, active=True))
    # Inactive slot on a different disease: the (user, disease, lab) key is unique.
    db_session.add(UserDiseaseUnitRole(user_id=user.id, disease_id=other_disease.id, lab_unit_id=lab.id,
                                       can_arbitrate=True, active=False))
    db_session.flush()

    grants = resolve_grants(db_session, user).of(GrantSource.GRADING_SLOT)
    assert len(grants) == 1
    assert grants[0].attr("can_grade_resident") is True
    assert grants[0].attr("disease_id") == disease.id


# --- request memoisation ----------------------------------------------------

def test_resolution_is_memoised_within_a_request(app, db_session):
    user = _user(db_session, "resident")
    with app.test_request_context():
        first = resolve_grants(db_session, user)
        second = resolve_grants(db_session, user)
    assert first is second


def test_memo_is_keyed_by_user(app, db_session):
    a, b = _user(db_session, "resident"), _user(db_session, "resident")
    with app.test_request_context():
        assert resolve_grants(db_session, a).actor.id != resolve_grants(db_session, b).actor.id
