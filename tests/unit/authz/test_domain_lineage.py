from types import SimpleNamespace

import pytest

from authz import AuthorizationDenied, RecordWorld, access_context
from models import User
from services.uploads.access import upload_record_scope
from tasks.access import task_record_scope


def test_upload_lineage_distinguishes_classical_and_project_records():
    classical = upload_record_scope(
        SimpleNamespace(project_id=None, hospital_id=3, lab_unit_id=7)
    )
    project = upload_record_scope(
        SimpleNamespace(project_id=11, hospital_id=3, lab_unit_id=7)
    )

    assert classical.world == RecordWorld.CLASSICAL
    assert classical.project_id is None
    assert project.world == RecordWorld.PROJECT
    assert project.project_id == 11


def test_upload_lineage_missing_required_fact_denies():
    with pytest.raises(AuthorizationDenied):
        upload_record_scope(
            SimpleNamespace(project_id=11, hospital_id=None, lab_unit_id=7)
        )


def test_task_lineage_uses_maintained_project_and_lab_hospital(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_a1"])
    actor = User(username="lineage_actor", password_hash="x", is_active=True)
    db_session.add(actor)
    db_session.flush()
    context = access_context(db_session, actor)

    classical = task_record_scope(
        context,
        SimpleNamespace(project_id=None, lab_unit_id=lab.id),
    )
    project = task_record_scope(
        context,
        SimpleNamespace(project_id=101, lab_unit_id=lab.id),
    )
    assert classical.world == RecordWorld.CLASSICAL
    assert project.world == RecordWorld.PROJECT
    assert project.hospital_id == lab.hospital_id

    with pytest.raises(AuthorizationDenied):
        task_record_scope(
            context,
            SimpleNamespace(project_id=None, lab_unit_id=99999999),
        )
