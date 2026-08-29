from models import Role, User
from admin.user_management_authorization import can_manage_user
from admin.users import _replace_global_user_roles
from tests.helpers.factories import UserFactory


def _role(db, name: str) -> Role:
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def test_system_admin_role_edit_replaces_visible_global_roles(db_session):
    admin = UserFactory.create_admin(db_session, username="role_replace_admin")
    target = User(
        username="role_replace_target",
        password_hash="x",
        is_active=True,
        roles=[
            _role(db_session, "ophthalmologist"),
            _role(db_session, "analytics_viewer"),
            _role(db_session, "dataset_creator"),
            _role(db_session, "data_exporter"),
        ],
    )
    db_session.add(target)
    db_session.flush()

    _replace_global_user_roles(
        db_session,
        actor=admin,
        user=target,
        selected_role_names={"ophthalmologist"},
        valid_role_names={
            "ophthalmologist",
            "analytics_viewer",
            "dataset_creator",
            "data_exporter",
        },
    )

    assert {role.name for role in target.roles} == {"ophthalmologist"}


def test_global_role_edit_preserves_hidden_project_only_association(db_session):
    admin = UserFactory.create_admin(db_session, username="role_preserve_admin")
    target = User(
        username="role_preserve_target",
        password_hash="x",
        is_active=True,
        roles=[
            _role(db_session, "ophthalmologist"),
            _role(db_session, "project_admin"),
        ],
    )
    db_session.add(target)
    db_session.flush()

    _replace_global_user_roles(
        db_session,
        actor=admin,
        user=target,
        selected_role_names={"optometrist"},
        valid_role_names={"ophthalmologist", "optometrist"},
    )

    assert {role.name for role in target.roles} == {
        "optometrist",
        "project_admin",
    }


def test_user_manager_cannot_add_protected_roles(db_session):
    actor = UserFactory.create_by_role(
        db_session,
        "user_manager",
        username="role_user_manager",
    )
    target = User(
        username="role_local_target",
        password_hash="x",
        is_active=True,
        roles=[_role(db_session, "ophthalmologist")],
    )
    db_session.add(target)
    db_session.flush()

    _replace_global_user_roles(
        db_session,
        actor=actor,
        user=target,
        selected_role_names={
            "admin",
            "user_manager",
            "local_admin",
            "pii_exporter",
            "ophthalmologist",
        },
        valid_role_names={
            "admin",
            "user_manager",
            "local_admin",
            "pii_exporter",
            "ophthalmologist",
        },
    )

    assert {role.name for role in target.roles} == {"ophthalmologist"}


def test_user_manager_target_boundary_is_same_hospital_nonself_and_unprivileged(
    db_session, core_test_data
):
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    hospital_b = db_session.merge(core_test_data["hospital_b"])
    actor = UserFactory.create_by_role(
        db_session,
        "user_manager",
        username="target_boundary_manager",
    )
    actor.hospital_id = hospital_a.id
    ordinary = User(
        username="target_boundary_ordinary",
        password_hash="x",
        is_active=True,
        hospital_id=hospital_a.id,
        roles=[_role(db_session, "ophthalmologist")],
    )
    cross_hospital = User(
        username="target_boundary_cross",
        password_hash="x",
        is_active=True,
        hospital_id=hospital_b.id,
    )
    privileged = User(
        username="target_boundary_privileged",
        password_hash="x",
        is_active=True,
        hospital_id=hospital_a.id,
        roles=[_role(db_session, "local_admin")],
    )
    db_session.add_all([ordinary, cross_hospital, privileged])
    db_session.flush()

    assert can_manage_user(actor=actor, target_user=ordinary)
    assert not can_manage_user(actor=actor, target_user=actor)
    assert not can_manage_user(actor=actor, target_user=cross_hospital)
    assert not can_manage_user(actor=actor, target_user=privileged)
