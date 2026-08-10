from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from auth.utils import utcnow
from grading.workbench.configuration import configuration_snapshot
from grading.workbench.errors import AnnotationPolicyChanged, SessionSuperseded
from grading.workbench.models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from grading.workbench.sessions import (
    expire_stale,
    heartbeat,
    issue_token,
    list_active,
    new_session_times,
    resume,
)
from models import GradingTask
from tests.helpers.test_factories import TestDataFactory


def _encounter_task(db, *, disease_id: int, lab_unit_id: int):
    encounter = TestDataFactory.create_patient_encounter(
        db,
        lab_unit_id=lab_unit_id,
        patient_id=f"WORKBENCH-{utcnow().timestamp()}",
    )
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=disease_id,
        lab_unit_id=lab_unit_id,
        state="pending",
        grading_target_level="encounter",
        task_source="workbench_test",
    )
    db.add(task)
    db.flush()
    return task


def _session(db, *, user_id: int, task: GradingTask):
    snapshot, fingerprint = configuration_snapshot(
        db, tasks=[task], workflow="ordinary", role_slot="resident"
    )
    raw_token, token_hash = issue_token()
    acquired, idle, absolute = new_session_times()
    session = GradingWorkbenchSession(
        user_id=user_id,
        role_slot="resident",
        workflow="ordinary",
        root_task_id=task.id,
        token_hash=token_hash,
        configuration_snapshot_json=snapshot,
        configuration_fingerprint=fingerprint,
        acquired_at=acquired,
        last_heartbeat_at=acquired,
        idle_expires_at=idle,
        absolute_expires_at=absolute,
    )
    session.targets.append(GradingWorkbenchSessionTarget(
        task_id=task.id,
        role_slot="resident",
        target_order=0,
        acquired_task_state=task.state,
        acquired_at=acquired,
    ))
    db.add(session)
    db.flush()
    return session, raw_token


def test_active_session_is_unique_per_user_and_role(db_session, resident_user, core_test_data):
    user = db_session.merge(resident_user)
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    first_task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    second_task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    _session(db_session, user_id=user.id, task=first_task)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        _session(db_session, user_id=user.id, task=second_task)


def test_active_target_lease_is_unique_across_users(db_session, test_users, core_test_data):
    first_user = db_session.merge(test_users["resident"])
    second_user = db_session.merge(test_users["ophthalmologist"])
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    _session(db_session, user_id=first_user.id, task=task)

    with pytest.raises(IntegrityError), db_session.begin_nested():
        _session(db_session, user_id=second_user.id, task=task)


def test_resume_rotates_token_and_old_tab_is_superseded(db_session, resident_user, core_test_data):
    user = db_session.merge(resident_user)
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    session, old_token = _session(db_session, user_id=user.id, task=task)

    workbench, new_token = resume(db_session, session_uuid=session.uuid, user_id=user.id)

    assert new_token != old_token
    assert workbench.lease.token_generation == 2
    with pytest.raises(SessionSuperseded):
        heartbeat(
            db_session,
            session_uuid=session.uuid,
            user_id=user.id,
            raw_token=old_token,
            token_generation=1,
        )


def test_heartbeat_never_extends_absolute_expiry(db_session, resident_user, core_test_data):
    user = db_session.merge(resident_user)
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    session, token = _session(db_session, user_id=user.id, task=task)
    session.absolute_expires_at = utcnow() + timedelta(minutes=10)

    result = heartbeat(
        db_session,
        session_uuid=session.uuid,
        user_id=user.id,
        raw_token=token,
        token_generation=1,
    )

    assert result["idle_expires_at"] == session.absolute_expires_at.isoformat()


def test_active_session_listing_supports_resume_without_exposing_token(
    db_session, resident_user, core_test_data
):
    user = db_session.merge(resident_user)
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    session, _token = _session(db_session, user_id=user.id, task=task)

    rows = list_active(db_session, user_id=user.id)

    assert rows == [{
        "session_uuid": session.uuid,
        "role_slot": "resident",
        "workflow": "ordinary",
        "acquired_at": session.acquired_at.isoformat(),
        "idle_expires_at": session.idle_expires_at.isoformat(),
        "absolute_expires_at": session.absolute_expires_at.isoformat(),
        "target_count": 1,
        "can_resume": True,
    }]
    assert "token" not in rows[0]


def test_expiry_releases_target_without_changing_task_state(
    db_session, resident_user, core_test_data
):
    user = db_session.merge(resident_user)
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["glaucoma"])
    task = _encounter_task(db_session, disease_id=disease.id, lab_unit_id=lab.id)
    session, _token = _session(db_session, user_id=user.id, task=task)
    session.idle_expires_at = utcnow() - timedelta(seconds=1)
    db_session.flush()

    assert expire_stale(db_session) == 1
    assert session.status == "expired"
    assert session.targets[0].released_at is not None
    assert task.state == "pending"
