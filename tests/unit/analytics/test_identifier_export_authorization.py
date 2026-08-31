import pytest

from analytics.encounter_exports import (
    EncounterExportFilters,
    identifier_release_encounter_ids,
)
from authz.exceptions import AuthorizationDenied
from data_authorization.models import PROJECT_SCOPE, ProjectRoleGrant
from models import Project, Role, User


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def test_identifier_export_without_ordinary_scope_denies(db_session):
    actor = User(username="pii_export_no_scope", password_hash="x", is_active=True)
    actor.roles = [_role(db_session, "pii_exporter")]
    db_session.add(actor)
    db_session.flush()

    with pytest.raises(AuthorizationDenied) as denied:
        identifier_release_encounter_ids(
            db_session, actor, EncounterExportFilters()
        )
    assert denied.value.reason == "export_scope_missing"


def test_admin_break_glass_can_receive_authorized_empty_export(db_session):
    actor = User(username="pii_export_admin", password_hash="x", is_active=True)
    actor.roles = [_role(db_session, "admin")]
    db_session.add(actor)
    db_session.flush()

    assert identifier_release_encounter_ids(
        db_session, actor, EncounterExportFilters()
    ) == []


def test_mixed_authorized_and_unauthorized_project_filters_deny(db_session):
    allowed_project = Project(title="Allowed PII", code="PII_ALLOWED", active=True)
    denied_project = Project(title="Denied PII", code="PII_DENIED", active=True)
    actor = User(username="pii_export_mixed", password_hash="x", is_active=True)
    db_session.add_all([allowed_project, denied_project, actor])
    db_session.flush()
    db_session.add(
        ProjectRoleGrant(
            project_id=allowed_project.id,
            user_id=actor.id,
            role_id=_role(db_session, "pii_exporter").id,
            scope_type=PROJECT_SCOPE,
            lab_unit_id=None,
            active=True,
        )
    )
    db_session.flush()

    with pytest.raises(AuthorizationDenied):
        identifier_release_encounter_ids(
            db_session,
            actor,
            EncounterExportFilters(
                project_ids=(allowed_project.id, denied_project.id)
            ),
        )
