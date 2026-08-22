import pytest
from contextlib import contextmanager

from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from models import Project, Role, User
from project_configuration.models import ProjectLabUnit
from project_configuration.service import (
    ProjectLabConfigurationDenied,
    configured_project_lab_unit_ids,
    replace_project_lab_units,
)
from tests.helpers.factories import UserFactory
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
)
from upload_profiles import admin_service as upload_profile_admin_service


def _role(db, name: str) -> Role:
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _user(db, username: str) -> User:
    user = User(username=username, password_hash="x", is_active=True)
    db.add(user)
    db.flush()
    return user


def _project(db, code: str) -> Project:
    project = Project(title=f"Boundary {code}", code=code, active=True)
    db.add(project)
    db.flush()
    return project


def test_only_system_admin_can_replace_project_lab_units(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    project = _project(db_session, "LAB_ADMIN_ONLY")
    project_admin = _user(db_session, "boundary_project_admin")
    db_session.add(ProjectRoleGrant(
        project_id=project.id,
        user_id=project_admin.id,
        role_id=_role(db_session, "project_admin").id,
        scope_type=PROJECT_SCOPE,
        active=True,
    ))
    db_session.flush()

    with pytest.raises(ProjectLabConfigurationDenied):
        replace_project_lab_units(
            db_session,
            actor=project_admin,
            project_id=project.id,
            lab_unit_ids=[lab.id],
        )


def test_replacing_boundary_deactivates_out_of_scope_access_rows(db_session, core_test_data):
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    admin = UserFactory.create_admin(db_session, username="boundary_system_admin")
    target = _user(db_session, "boundary_target")
    project = _project(db_session, "LAB_NARROW")
    db_session.add_all([
        ProjectLabUnit(project_id=project.id, lab_unit_id=lab_a.id, active=True),
        ProjectLabUnit(project_id=project.id, lab_unit_id=lab_b.id, active=True),
    ])
    grant = ProjectRoleGrant(
        project_id=project.id,
        user_id=target.id,
        role_id=_role(db_session, "verifier").id,
        scope_type=LAB_UNIT_SCOPE,
        lab_unit_id=lab_b.id,
        active=True,
    )
    profile = UploadProfile(name="Boundary direct profile")
    project_profile = ProjectUploadProfile(project_id=project.id, profile=profile, active=True)
    assignment = ProjectUploadProfileAssignment(
        project_profile=project_profile,
        user_id=target.id,
        lab_unit_id=lab_b.id,
        active=True,
    )
    db_session.add_all([grant, assignment])
    db_session.flush()

    replace_project_lab_units(
        db_session,
        actor=admin,
        project_id=project.id,
        lab_unit_ids=[lab_a.id],
    )

    assert configured_project_lab_unit_ids(db_session, project_id=project.id) == {lab_a.id}
    assert grant.active is False
    assert assignment.active is False


def test_project_admin_cannot_change_project_lab_unit_api(
    app,
    db_session,
    core_test_data,
):
    lab = db_session.merge(core_test_data["lab_a1"])
    project = _project(db_session, "LAB_API_ADMIN")
    project_admin = UserFactory.create_by_role(
        db_session,
        "project_admin",
        username="boundary_api_project_admin",
    )
    db_session.flush()

    with app.test_client(user=project_admin) as project_admin_client:
        denied = project_admin_client.put(
            f"/api/projects/{project.id}/lab-units",
            json={"lab_unit_ids": [lab.id]},
        )
    assert denied.status_code == 403


def test_project_admin_cannot_change_upload_profile_configuration(
    db_session,
    monkeypatch,
):
    project_admin = UserFactory.create_by_role(
        db_session,
        "project_admin",
        username="profile_service_project_admin",
    )
    profile = UploadProfile(name="Protected profile", active=True)
    db_session.add(profile)
    db_session.flush()

    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(upload_profile_admin_service, "transaction_scope", use_test_session)

    result = upload_profile_admin_service.set_profile_active(
        project_admin.id,
        profile.id,
        False,
    )

    assert result.status_code == 403
    assert profile.active is True
