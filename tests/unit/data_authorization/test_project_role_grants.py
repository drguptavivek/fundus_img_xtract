import pytest

from data_authorization.dto import ProjectRoleGrantInput
from data_authorization.exceptions import ProjectGrantPermissionDenied, ProjectGrantValidationError
from data_authorization.models import HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from data_authorization.service import (
    deactivate_project_role_grant,
    list_project_role_grants,
    replace_project_role_grants,
    upsert_project_role_grant,
    user_has_project_role,
)
from models import Project, Role, User
from tests.helpers.factories import UserFactory
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


def _project(db, suffix: str) -> Project:
    project = Project(title=f"Authorization Project {suffix}", code=f"AUTH_{suffix}", active=True)
    db.add(project)
    db.flush()
    return project


def _configure_labs(db, project: Project, *lab_ids: int) -> None:
    db.add_all(ProjectLabUnit(project_id=project.id, lab_unit_id=lab_id, active=True) for lab_id in lab_ids)
    db.flush()


def test_project_grant_uses_global_role_catalog_and_is_membership(db_session, core_test_data):
    admin = UserFactory.create_admin(db_session, username="grant_catalog_admin")
    target = _user(db_session, "grant_catalog_target")
    project = _project(db_session, "CATALOG")
    collaborator = _role(db_session, "collaborator")

    dto = upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name=collaborator.name,
            scope_type=PROJECT_SCOPE,
        ),
    )

    row = db_session.get(ProjectRoleGrant, dto.id)
    assert row.role_id == collaborator.id
    assert target.roles == []
    assert user_has_project_role(
        db_session,
        user_id=target.id,
        project_id=project.id,
        role_names={"collaborator"},
    )


def test_site_pi_is_a_title_and_cannot_manage_project_access(db_session, core_test_data):
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    hospital_b = db_session.merge(core_test_data["hospital_b"])
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    admin = UserFactory.create_admin(db_session, username="grant_site_admin")
    site_pi = _user(db_session, "grant_site_pi")
    collaborator = _user(db_session, "grant_site_collaborator")
    project = _project(db_session, "SITE")
    _configure_labs(db_session, project, lab_a.id, lab_b.id)
    _role(db_session, "site_pi")
    _role(db_session, "collaborator")

    upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=site_pi.id,
            role_name="site_pi",
            scope_type=HOSPITAL_SCOPE,
            hospital_id=hospital_a.id,
        ),
    )
    for lab in (lab_a, lab_b):
        with pytest.raises(ProjectGrantPermissionDenied):
            upsert_project_role_grant(
                db_session,
                actor=site_pi,
                data=ProjectRoleGrantInput(
                    project_id=project.id,
                    user_id=collaborator.id,
                    role_name="collaborator",
                    scope_type=LAB_UNIT_SCOPE,
                    lab_unit_id=lab.id,
                ),
            )

    assert hospital_a.id != hospital_b.id


def test_project_admin_manages_operational_roles_across_configured_project_labs(db_session, core_test_data):
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    admin = UserFactory.create_admin(db_session, username="grant_project_admin_seed")
    project_admin = _user(db_session, "grant_project_admin")
    collaborator = _user(db_session, "grant_project_collaborator")
    project = _project(db_session, "PROJECT_ADMIN")
    _configure_labs(db_session, project, lab_a.id, lab_b.id)
    _role(db_session, "project_admin")
    _role(db_session, "collaborator")
    _role(db_session, "site_pi")

    upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=project_admin.id,
            role_name="project_admin",
            scope_type=HOSPITAL_SCOPE,
            hospital_id=hospital_a.id,
        ),
    )
    allowed = upsert_project_role_grant(
        db_session,
        actor=project_admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=collaborator.id,
            role_name="collaborator",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
        ),
    )
    assert allowed.lab_unit_id == lab_a.id

    second = upsert_project_role_grant(
        db_session,
        actor=project_admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=collaborator.id,
            role_name="collaborator",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_b.id,
        ),
    )
    assert second.lab_unit_id == lab_b.id

    with pytest.raises(ProjectGrantPermissionDenied):
        upsert_project_role_grant(
            db_session,
            actor=project_admin,
            data=ProjectRoleGrantInput(
                project_id=project.id,
                user_id=collaborator.id,
                role_name="site_pi",
                scope_type=HOSPITAL_SCOPE,
                hospital_id=hospital_a.id,
            ),
        )


def test_legacy_global_roles_are_not_assignable_as_project_roles(db_session, core_test_data):
    hospital = db_session.merge(core_test_data["hospital_a"])
    lab = db_session.merge(core_test_data["lab_a1"])
    admin = UserFactory.create_admin(db_session, username="grant_multi_admin")
    target = _user(db_session, "grant_multi_target")
    project = _project(db_session, "MULTI")
    _configure_labs(db_session, project, lab.id)
    _role(db_session, "data_manager")
    _role(db_session, "fileUploader")

    for data in (
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="data_manager",
            scope_type=HOSPITAL_SCOPE,
            hospital_id=hospital.id,
        ),
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="fileUploader",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab.id,
        ),
    ):
        with pytest.raises(ProjectGrantValidationError):
            upsert_project_role_grant(db_session, actor=admin, data=data)

    assert list_project_role_grants(db_session, actor=admin, project_id=project.id) == ()
    assert not target.has_role("data_manager", "fileUploader")


def test_inactive_grant_removes_membership(db_session):
    admin = UserFactory.create_admin(db_session, username="grant_inactive_admin")
    target = _user(db_session, "grant_inactive_target")
    project = _project(db_session, "INACTIVE")
    _role(db_session, "collaborator")
    data = ProjectRoleGrantInput(
        project_id=project.id,
        user_id=target.id,
        role_name="collaborator",
        scope_type=PROJECT_SCOPE,
    )
    upsert_project_role_grant(db_session, actor=admin, data=data)
    upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(**{**data.__dict__, "active": False}),
    )
    assert not user_has_project_role(
        db_session,
        user_id=target.id,
        project_id=project.id,
        role_names={"collaborator"},
    )


def test_replace_roles_can_move_scope_and_remove_grants(db_session, core_test_data, caplog):
    hospital = db_session.merge(core_test_data["hospital_a"])
    lab = db_session.merge(core_test_data["lab_a1"])
    admin = UserFactory.create_admin(db_session, username="grant_edit_admin")
    target = _user(db_session, "grant_edit_target")
    project = _project(db_session, "EDIT")
    _configure_labs(db_session, project, lab.id)
    _role(db_session, "collaborator")
    _role(db_session, "analytics_viewer")

    with caplog.at_level("INFO", logger="project_authorization"):
        created = replace_project_role_grants(
            db_session,
            actor=admin,
            project_id=project.id,
            user_id=target.id,
            role_names={"collaborator", "analytics_viewer"},
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab.id,
        )
        moved = replace_project_role_grants(
            db_session,
            actor=admin,
            project_id=project.id,
            user_id=target.id,
            role_names={"analytics_viewer"},
            scope_type=HOSPITAL_SCOPE,
            hospital_id=hospital.id,
            original_scope_type=LAB_UNIT_SCOPE,
            original_lab_unit_id=lab.id,
        )
        removed = deactivate_project_role_grant(
            db_session,
            actor=admin,
            project_id=project.id,
            grant_id=moved[0].id,
        )

    assert {grant.role_name for grant in created} == {"collaborator", "analytics_viewer"}
    assert [grant.role_name for grant in moved] == ["analytics_viewer"]
    assert removed.active is False
    assert not user_has_project_role(
        db_session,
        user_id=target.id,
        project_id=project.id,
        role_names={"collaborator", "analytics_viewer"},
        hospital_id=hospital.id,
        lab_unit_id=lab.id,
    )
    messages = "\n".join(caplog.messages)
    assert "change=created" in messages
    assert "change=scope_removed" in messages
    assert "change=removed" in messages
    assert f"actor_user_id={admin.id}" in messages
    assert f"target_user_id={target.id}" in messages
