from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from authz_v2.domain.models import AuthorizationGrant
from authz_v2.repositories.grants import GrantRepository
from models import Hospital, LabUnit, User
from models import Role as RoleModel


def _user(db_session, prefix: str) -> User:
    user = User(
        username=f"{prefix}_{uuid4().hex}",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _role(db_session, name: str) -> RoleModel:
    return db_session.scalar(select(RoleModel).where(RoleModel.name == name))


def test_manageable_grants_are_scoped_in_sql_before_loading(db_session):
    hospital_a = Hospital(name=f"authz-a-{uuid4().hex}")
    hospital_b = Hospital(name=f"authz-b-{uuid4().hex}")
    db_session.add_all((hospital_a, hospital_b))
    db_session.flush()
    lab_a = LabUnit(name=f"lab-a-{uuid4().hex}", hospital_id=hospital_a.id)
    lab_b = LabUnit(name=f"lab-b-{uuid4().hex}", hospital_id=hospital_b.id)
    db_session.add_all((lab_a, lab_b))
    actor = _user(db_session, "local_admin")
    target_a = _user(db_session, "target_a")
    target_b = _user(db_session, "target_b")
    db_session.flush()

    local_admin = _role(db_session, "local_admin")
    analytics = _role(db_session, "analytics_viewer")
    assert local_admin is not None and analytics is not None
    actor_grant = AuthorizationGrant(
        user_id=actor.id,
        role_id=local_admin.id,
        scope_type="hospital",
        hospital_id=hospital_a.id,
        active=True,
    )
    visible = AuthorizationGrant(
        user_id=target_a.id,
        role_id=analytics.id,
        scope_type="lab_unit",
        lab_unit_id=lab_a.id,
        active=True,
    )
    hidden = AuthorizationGrant(
        user_id=target_b.id,
        role_id=analytics.id,
        scope_type="lab_unit",
        lab_unit_id=lab_b.id,
        active=True,
    )
    db_session.add_all((actor_grant, visible, hidden))
    db_session.flush()

    rows = GrantRepository(db_session).list_manageable(actor.id)

    assert {row.id for row in rows} == {visible.id}
    assert rows[0].scope.hospital_id == hospital_a.id
