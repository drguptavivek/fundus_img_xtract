from models import Role, User
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


def test_local_admin_cannot_add_system_admin_role(db_session):
    actor = UserFactory.create_by_role(
        db_session,
        "local_admin",
        username="role_local_admin",
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
        selected_role_names={"admin", "ophthalmologist"},
        valid_role_names={"admin", "ophthalmologist"},
    )

    assert {role.name for role in target.roles} == {"ophthalmologist"}
