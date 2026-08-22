from data_authorization.models import HOSPITAL_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from data_authorization.policy import (
    ACTION_MANAGE_ACCESS,
    ACTION_VIEW,
    ACTION_WAI_RESULTS,
    ACTION_WAI_RUN,
    user_can_project_action,
)
from models import Project, Role, User
from project_configuration.models import ProjectLabUnit


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
    project = Project(title=f"Policy {code}", code=code, active=True)
    db.add(project)
    db.flush()
    return project


def _grant(db, *, user, project, role_name, scope_type=PROJECT_SCOPE, hospital_id=None):
    db.add(ProjectRoleGrant(
        project_id=project.id,
        user_id=user.id,
        role_id=_role(db, role_name).id,
        scope_type=scope_type,
        hospital_id=hospital_id,
        active=True,
    ))
    db.commit()


def test_global_operational_role_does_not_leak_into_project_authority(db_session):
    user = _user(db_session, "policy_global_verifier")
    project = _project(db_session, "POLICY_GLOBAL")
    user.roles.append(_role(db_session, "verifier"))
    db_session.commit()

    assert not user_can_project_action(
        db_session, user=user, project_id=project.id, action=ACTION_WAI_RUN
    )
    assert not user_can_project_action(
        db_session, user=user, project_id=project.id, action=ACTION_VIEW
    )


def test_project_wai_role_matrix_has_no_implicit_task_authority(db_session):
    project = _project(db_session, "POLICY_WAI")
    role_expectations = {
        "project_pi": (False, True, False),
        "site_pi": (False, True, False),
        "project_admin": (False, True, True),
        "verifier": (True, False, False),
        "optometrist": (True, True, False),
        "ophthalmologist": (False, False, False),
    }

    for index, (role_name, expected) in enumerate(role_expectations.items()):
        user = _user(db_session, f"policy_matrix_{index}")
        _grant(db_session, user=user, project=project, role_name=role_name)
        can_run, can_results, can_manage = expected
        assert user_can_project_action(
            db_session, user=user, project_id=project.id, action=ACTION_WAI_RUN
        ) is can_run
        assert user_can_project_action(
            db_session, user=user, project_id=project.id, action=ACTION_WAI_RESULTS
        ) is can_results
        assert user_can_project_action(
            db_session, user=user, project_id=project.id, action=ACTION_MANAGE_ACCESS
        ) is can_manage


def test_project_boundary_not_admin_grant_scope_controls_access(db_session, core_test_data):
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    project = _project(db_session, "POLICY_SCOPE")
    db_session.add(ProjectLabUnit(project_id=project.id, lab_unit_id=lab_a.id, active=True))
    db_session.flush()
    user = _user(db_session, "policy_scoped_admin")
    _grant(
        db_session,
        user=user,
        project=project,
        role_name="project_admin",
        scope_type=HOSPITAL_SCOPE,
        hospital_id=hospital_a.id,
    )

    assert user_can_project_action(
        db_session,
        user=user,
        project_id=project.id,
        action=ACTION_MANAGE_ACCESS,
        lab_unit_id=lab_a.id,
    )
    assert user_can_project_action(
        db_session,
        user=user,
        project_id=project.id,
        action=ACTION_MANAGE_ACCESS,
        lab_unit_id=lab_b.id,
    ) is False
