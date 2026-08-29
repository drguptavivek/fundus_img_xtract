import pytest

from data_authorization.dto import ProjectRoleGrantInput
from data_authorization.exceptions import ProjectGrantPermissionDenied, ProjectGrantValidationError
from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
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
from authz.privilege_escalation_mitigation import (
    DelegatorGrant,
    delegable_project_roles,
)


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


def test_privilege_escalation_mitigation_fails_closed_on_missing_scope_facts():
    grant = DelegatorGrant(
        role_name="project_pi",
        scope_type=LAB_UNIT_SCOPE,
        lab_unit_id=7,
    )
    assert delegable_project_roles(
        actor_user_id=1,
        target_user_id=2,
        actor_is_admin=False,
        requested_scope_type=LAB_UNIT_SCOPE,
        requested_lab_unit_id=None,
        delegator_grants=[grant],
    ) == frozenset()
    assert delegable_project_roles(
        actor_user_id=1,
        target_user_id=2,
        actor_is_admin=False,
        requested_scope_type=LAB_UNIT_SCOPE,
        requested_lab_unit_id=8,
        delegator_grants=[grant],
    ) == frozenset()


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


def test_site_pi_delegates_only_project_admin_inside_exact_scope(db_session, core_test_data):
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    admin = UserFactory.create_admin(db_session, username="grant_site_admin")
    site_pi = _user(db_session, "grant_site_pi")
    project_admin = _user(db_session, "grant_site_project_admin")
    project = _project(db_session, "SITE")
    _configure_labs(db_session, project, lab_a.id, lab_b.id)
    _role(db_session, "site_pi")
    _role(db_session, "project_admin")

    upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=site_pi.id,
            role_name="site_pi",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
        ),
    )
    allowed = upsert_project_role_grant(
        db_session,
        actor=site_pi,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=project_admin.id,
            role_name="project_admin",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
        ),
    )
    assert allowed.lab_unit_id == lab_a.id

    forbidden = (
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=project_admin.id,
            role_name="project_admin",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_b.id,
        ),
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=project_admin.id,
            role_name="project_admin",
            scope_type=PROJECT_SCOPE,
        ),
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=site_pi.id,
            role_name="project_admin",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
        ),
    )
    for data in forbidden:
        with pytest.raises(ProjectGrantPermissionDenied):
            upsert_project_role_grant(db_session, actor=site_pi, data=data)


def test_project_admin_delegates_operations_only_inside_own_scope(db_session, core_test_data):
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
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
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

    forbidden = (
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=collaborator.id,
            role_name="collaborator",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_b.id,
        ),
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=collaborator.id,
            role_name="site_pi",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
        ),
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=project_admin.id,
            role_name="collaborator",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab_a.id,
        ),
    )
    for data in forbidden:
        with pytest.raises(ProjectGrantPermissionDenied):
            upsert_project_role_grant(db_session, actor=project_admin, data=data)


def test_only_project_wide_project_admin_can_delegate_pii_exporter(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    admin = UserFactory.create_admin(db_session, username="grant_pii_seed_admin")
    wide_admin = _user(db_session, "grant_pii_wide_admin")
    site_admin = _user(db_session, "grant_pii_site_admin")
    target = _user(db_session, "grant_pii_target")
    project = _project(db_session, "PII_CEILING")
    _configure_labs(db_session, project, lab.id)
    for name in ("project_admin", "pii_exporter"):
        _role(db_session, name)

    for user, scope_type, lab_unit_id in (
        (wide_admin, PROJECT_SCOPE, None),
        (site_admin, LAB_UNIT_SCOPE, lab.id),
    ):
        upsert_project_role_grant(
            db_session,
            actor=admin,
            data=ProjectRoleGrantInput(
                project_id=project.id,
                user_id=user.id,
                role_name="project_admin",
                scope_type=scope_type,
                lab_unit_id=lab_unit_id,
            ),
        )

    granted = upsert_project_role_grant(
        db_session,
        actor=wide_admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="pii_exporter",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab.id,
        ),
    )
    assert granted.role_name == "pii_exporter"
    with pytest.raises(ProjectGrantPermissionDenied):
        upsert_project_role_grant(
            db_session,
            actor=site_admin,
            data=ProjectRoleGrantInput(
                project_id=project.id,
                user_id=target.id,
                role_name="pii_exporter",
                scope_type=LAB_UNIT_SCOPE,
                lab_unit_id=lab.id,
            ),
        )


def test_only_admin_appoints_pi_roles(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    admin = UserFactory.create_admin(db_session, username="grant_pi_admin")
    project_pi = _user(db_session, "grant_project_pi")
    target = _user(db_session, "grant_second_pi")
    project = _project(db_session, "PI_MATRIX")
    _configure_labs(db_session, project, lab.id)
    _role(db_session, "project_pi")
    _role(db_session, "site_pi")
    upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=project_pi.id,
            role_name="project_pi",
            scope_type=PROJECT_SCOPE,
        ),
    )
    with pytest.raises(ProjectGrantPermissionDenied):
        upsert_project_role_grant(
            db_session,
            actor=project_pi,
            data=ProjectRoleGrantInput(
                project_id=project.id,
                user_id=target.id,
                role_name="site_pi",
                scope_type=LAB_UNIT_SCOPE,
                lab_unit_id=lab.id,
            ),
        )


def test_project_data_manager_is_assignable_but_global_uploader_is_not(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    admin = UserFactory.create_admin(db_session, username="grant_multi_admin")
    target = _user(db_session, "grant_multi_target")
    project = _project(db_session, "MULTI")
    _configure_labs(db_session, project, lab.id)
    _role(db_session, "data_manager")
    _role(db_session, "fileUploader")

    granted = upsert_project_role_grant(
        db_session,
        actor=admin,
        data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="data_manager",
            scope_type=PROJECT_SCOPE,
        ),
    )
    assert granted.role_name == "data_manager"

    with pytest.raises(ProjectGrantValidationError):
        upsert_project_role_grant(
            db_session,
            actor=admin,
            data=ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="fileUploader",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab.id,
            ),
        )

    assert {row.role_name for row in list_project_role_grants(
        db_session, actor=admin, project_id=project.id
    )} == {"data_manager"}
    assert not target.has_role("data_manager", "fileUploader")


def test_pi_role_scope_shapes_are_enforced_for_admin(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    admin = UserFactory.create_admin(db_session, username="grant_shape_admin")
    target = _user(db_session, "grant_shape_target")
    project = _project(db_session, "ROLE_SHAPES")
    _configure_labs(db_session, project, lab.id)
    _role(db_session, "project_pi")
    _role(db_session, "site_pi")

    invalid = (
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="project_pi",
            scope_type=LAB_UNIT_SCOPE,
            lab_unit_id=lab.id,
        ),
        ProjectRoleGrantInput(
            project_id=project.id,
            user_id=target.id,
            role_name="site_pi",
            scope_type=PROJECT_SCOPE,
        ),
    )
    for data in invalid:
        with pytest.raises(ProjectGrantValidationError):
            upsert_project_role_grant(db_session, actor=admin, data=data)


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
            scope_type=PROJECT_SCOPE,
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
        lab_unit_id=lab.id,
    )
    messages = "\n".join(caplog.messages)
    assert "change=created" in messages
    assert "change=scope_removed" in messages
    assert "change=removed" in messages
    assert f"actor_user_id={admin.id}" in messages
    assert f"target_user_id={target.id}" in messages
