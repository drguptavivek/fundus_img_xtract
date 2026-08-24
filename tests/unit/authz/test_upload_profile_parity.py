"""An upload assignment must reach the same rows in SQL as in the engine.

`_upload_step` actions carry ``GrantSource.UPLOAD_PROFILE``. The engine
matched it; the predicate compiler had no branch for it, so ``authorize``
allowed an assigned uploader's row while ``scope_query`` hid it. A list
screen and a single-row check must never disagree about a patient image.

The value is pinned as well as the agreement: two renderers that both deny
agree perfectly and are both wrong.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from authz import ResourceRef, authorize, scope_query
from authz.resolver import resolve_grants
from models import DirectImageUpload, Project, Role, User
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import ImageFactory
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
)

ACTION = "upload.direct.view"


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name); db.add(role); db.flush()
    return role


def _world(db, core_test_data, role_name, *, second_lab=False):
    """A user assigned to one upload profile, and a project row in that lab."""
    h1 = db.merge(core_test_data["hospital"])
    lab = db.merge(core_test_data["lab_unit"])

    proj = Project(title="up", code=f"UP_{uuid4().hex[:6]}", active=True)
    db.add(proj); db.flush()
    db.add(ProjectLabUnit(project_id=proj.id, lab_unit_id=lab.id, active=True))
    db.flush()

    user = User(username=f"up_{uuid4().hex[:8]}", password_hash="x", is_active=True,
                hospital_id=h1.id)
    user.roles = [_role(db, role_name)]
    db.add(user); db.flush()

    profile = UploadProfile(name=f"prof_{uuid4().hex[:6]}", active=True)
    db.add(profile); db.flush()
    pup = ProjectUploadProfile(project_id=proj.id, upload_profile_id=profile.id, active=True)
    db.add(pup); db.flush()
    db.add(ProjectUploadProfileAssignment(
        project_upload_profile_id=pup.id, user_id=user.id, lab_unit_id=lab.id, active=True))
    db.flush()

    row = ImageFactory.create_direct_upload(db, hospital_id=h1.id, lab_unit_id=lab.id)
    row.project_id = proj.id
    db.flush()
    return user, row


def _both(db, user, row):
    """(engine verdict, sql verdict) for one row."""
    resolved = resolve_grants(db, user)
    engine = authorize(
        resolved.actor, ACTION,
        ResourceRef(type="direct_image_uploads", id=row.id, attributes={
            "project_id": row.project_id, "hospital_id": row.hospital_id,
            "lab_unit_id": row.lab_unit_id}),
        grants=resolved.grants,
    ).allowed
    sql = row.id in set(db.execute(
        scope_query(select(DirectImageUpload.id).where(DirectImageUpload.id == row.id),
                    resolved, ACTION, DirectImageUpload)
    ).scalars())
    return engine, sql


@pytest.mark.parametrize("role_name", ["fileUploader", "optometrist", "field_optometrist"])
def test_engine_and_sql_agree_for_an_upload_assignment(db_session, core_test_data, role_name):
    user, row = _world(db_session, core_test_data, role_name)
    engine, sql = _both(db_session, user, row)
    assert engine == sql, (
        f"{role_name}: engine={engine} sql={sql} -- an upload assignment must "
        "reach the same rows through both renderers"
    )


@pytest.mark.parametrize("role_name", ["fileUploader", "optometrist"])
def test_an_upload_assignment_actually_reaches_its_project_lab(db_session, core_test_data, role_name):
    """Within an assigned (project, lab) an uploader sees every upload there.

    Not only their own: the reach is the lab, which is what lets an uploader
    follow automated ingestion they did not personally trigger.
    """
    user, row = _world(db_session, core_test_data, role_name)
    engine, sql = _both(db_session, user, row)
    assert engine and sql, f"{role_name}: engine={engine} sql={sql}"


def test_an_upload_assignment_does_not_reach_another_projects_row(db_session, core_test_data):
    """The grant names a (project, lab) pair; the project half still binds."""
    user, _row = _world(db_session, core_test_data, "fileUploader")
    other = Project(title="other", code=f"OT_{uuid4().hex[:6]}", active=True)
    db_session.add(other); db_session.flush()
    foreign = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=db_session.merge(core_test_data["hospital"]).id,
        lab_unit_id=db_session.merge(core_test_data["lab_unit"]).id,
    )
    foreign.project_id = other.id
    db_session.flush()

    engine, sql = _both(db_session, user, foreign)
    assert not engine and not sql, f"engine={engine} sql={sql}"
