import time

import pytest

from data_authorization.models import ProjectRoleGrant
from models import Project, Role, User
from project_configuration.models import ProjectLabUnit
from review.discrepancy_export import (
    authorized_export_project_grant_ids,
    authorized_export_project_lab_unit_ids,
    reauthorize_discrepancy_filters,
)


def _role(db, name: str) -> Role:
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _project_scope(db, *, actor, lab, role_name: str, scope_type: str, enabled: bool):
    project = Project(
        title=f"Discrepancy export {actor.username} {scope_type}",
        code=f"DX_{actor.id}_{scope_type}",
        active=True,
    )
    db.add(project)
    db.flush()
    boundary = ProjectLabUnit(
        project_id=project.id,
        lab_unit_id=lab.id,
        active=True,
        sites_can_export_grades=enabled,
    )
    grant = ProjectRoleGrant(
        project_id=project.id,
        user_id=actor.id,
        role_id=_role(db, role_name).id,
        scope_type=scope_type,
        lab_unit_id=lab.id if scope_type == "lab_unit" else None,
        active=True,
    )
    db.add_all([boundary, grant])
    db.flush()
    return project, boundary, grant


def test_site_export_flag_controls_site_scoped_grant(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = User(username="site_discrepancy_exporter", password_hash="x", is_active=True)
    db_session.add(actor)
    db_session.flush()
    project, boundary, grant = _project_scope(
        db_session,
        actor=actor,
        lab=lab,
        role_name="data_exporter",
        scope_type="lab_unit",
        enabled=False,
    )

    assert grant.id not in authorized_export_project_grant_ids(
        db_session, actor=actor, include_identifiers=False
    )
    assert not authorized_export_project_lab_unit_ids(
        db_session,
        actor=actor,
        project_id=project.id,
        include_identifiers=False,
    )

    boundary.sites_can_export_grades = True
    db_session.flush()
    assert grant.id in authorized_export_project_grant_ids(
        db_session, actor=actor, include_identifiers=False
    )
    assert authorized_export_project_lab_unit_ids(
        db_session,
        actor=actor,
        project_id=project.id,
        include_identifiers=False,
    ) == {lab.id}


def test_project_wide_export_grant_bypasses_site_flag(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = User(username="project_discrepancy_exporter", password_hash="x", is_active=True)
    db_session.add(actor)
    db_session.flush()
    project, _boundary, grant = _project_scope(
        db_session,
        actor=actor,
        lab=lab,
        role_name="data_exporter",
        scope_type="project",
        enabled=False,
    )

    assert grant.id in authorized_export_project_grant_ids(
        db_session, actor=actor, include_identifiers=False
    )
    assert authorized_export_project_lab_unit_ids(
        db_session,
        actor=actor,
        project_id=project.id,
        include_identifiers=False,
    ) == {lab.id}


def test_pii_export_route_requires_recent_reauthentication(
    app, db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = User(username="pii_discrepancy_exporter", password_hash="x", is_active=True)
    db_session.add(actor)
    db_session.flush()
    project, _boundary, _grant = _project_scope(
        db_session,
        actor=actor,
        lab=lab,
        role_name="pii_exporter",
        scope_type="project",
        enabled=False,
    )

    with app.test_client(user=actor) as client:
        response = client.post(
            "/review/discrepancy-export-pii",
            data={"project_id": project.id, "lab_unit_id": lab.id},
        )
        assert response.status_code == 302
        assert "/confirm-password" in response.headers["Location"]

        with client.session_transaction() as session:
            session["last_sudo_time"] = int(time.time())
        # Step-up now succeeds; transport validation fails closed because the
        # required disease fact was deliberately omitted.
        validated = client.post(
            "/review/discrepancy-export-pii",
            data={"project_id": project.id, "lab_unit_id": lab.id},
        )
        assert validated.status_code == 302
        assert "/confirm-password" not in validated.headers["Location"]


def test_worker_denies_after_site_or_grant_revocation(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = User(username="revoked_pii_discrepancy_exporter", password_hash="x", is_active=True)
    db_session.add(actor)
    db_session.flush()
    project, boundary, grant = _project_scope(
        db_session,
        actor=actor,
        lab=lab,
        role_name="pii_exporter",
        scope_type="lab_unit",
        enabled=True,
    )
    queued = {
        "authorization_action": "pii_export",
        "project_id": project.id,
        "allowed_lab_units": [lab.id],
    }
    assert reauthorize_discrepancy_filters(
        db_session, actor, queued
    )["project_capability_grant_ids"] == [grant.id]

    boundary.sites_can_export_grades = False
    db_session.flush()
    with pytest.raises(PermissionError, match="no longer covers"):
        reauthorize_discrepancy_filters(db_session, actor, queued)

    boundary.sites_can_export_grades = True
    grant.active = False
    db_session.flush()
    with pytest.raises(PermissionError, match="no longer covers"):
        reauthorize_discrepancy_filters(db_session, actor, queued)
