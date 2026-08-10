from __future__ import annotations

from grading.workbench.configuration import configuration_snapshot
from grading.workbench.models import (
    AnnotationSet,
    GradingSubmissionEvent,
    GradingSubmissionEventItem,
    GradingWorkbenchSession,
    GradingWorkbenchSessionTarget,
)
from grading.workbench.sessions import issue_token, new_session_times
from grading.workbench.submission import submit
from grading.workbench.history import submission_history
from grading.workbench.audit import record_rejected_submission
from models import Consensus, Grade, GradingTask
from tests.helpers.test_factories import TestDataFactory
from grading.workbench.state import apply_grade_state


def _leased_encounter_task(db, *, user, disease, lab):
    encounter = TestDataFactory.create_patient_encounter(
        db,
        lab_unit_id=lab.id,
        patient_id="WORKBENCH-SUBMISSION",
    )
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="pending",
        grading_target_level="encounter",
        task_source="workbench_test",
    )
    db.add(task)
    db.flush()
    snapshot, fingerprint = configuration_snapshot(
        db, tasks=[task], workflow="ordinary", role_slot="resident"
    )
    raw_token, token_hash = issue_token()
    acquired, idle, absolute = new_session_times()
    session = GradingWorkbenchSession(
        user_id=user.id,
        role_slot="resident",
        workflow="ordinary",
        root_task_id=task.id,
        token_hash=token_hash,
        configuration_snapshot_json=snapshot,
        configuration_fingerprint=fingerprint,
        queue_request_json={"disease_id": disease.id, "requested_slot": "resident"},
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
    return task, session, raw_token


def test_ordinary_submission_commits_grade_annotation_set_audit_and_lease_release(
    db_session,
    resident_user,
    core_test_data,
    disease_grading_glaucoma_normal,
):
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    lab = db_session.merge(core_test_data["lab_unit"])
    label = db_session.merge(disease_grading_glaucoma_normal)
    task, session, token = _leased_encounter_task(db_session, user=user, disease=disease, lab=lab)
    payload = {
        "action": "save_close",
        "idempotency_key": "ordinary-submission-1",
        "configuration_fingerprint": session.configuration_fingerprint,
        "observations": {
            task.uuid: {
                "disease_grading_id": label.id,
                "comment": "Normal encounter",
                "selected_feature_ids": [],
                "feature_geometry": None,
                "annotation_policy_revision": 1,
            }
        },
    }

    result = submit(
        db_session,
        session_uuid=session.uuid,
        user_id=user.id,
        raw_token=token,
        token_generation=1,
        payload=payload,
    )

    grade = db_session.query(Grade).filter_by(task_id=task.id, grader_user_id=user.id).one()
    annotation_set = db_session.query(AnnotationSet).filter_by(grade_id=grade.id).one()
    event = db_session.query(GradingSubmissionEvent).filter_by(uuid=result["event_uuid"]).one()
    item = db_session.query(GradingSubmissionEventItem).filter_by(event_id=event.id).one()
    assert task.state == "resident_done"
    assert grade.comment == "Normal encounter"
    assert annotation_set.instances == []
    assert event.outcome == "accepted"
    assert item.before_json is None
    assert item.after_json["disease_grading_id"] == label.id
    assert session.status == "completed"
    assert session.targets[0].released_at is not None
    history = submission_history(db_session, actor_user_id=user.id)
    assert history[0]["event_uuid"] == event.uuid
    assert history[0]["items"][0]["grade_revision"] == 1
    assert history[0]["items"][0]["annotation_set_uuid"] == annotation_set.uuid


def test_submission_idempotency_returns_original_event(
    db_session,
    resident_user,
    core_test_data,
    disease_grading_glaucoma_normal,
):
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    lab = db_session.merge(core_test_data["lab_unit"])
    label = db_session.merge(disease_grading_glaucoma_normal)
    task, session, token = _leased_encounter_task(db_session, user=user, disease=disease, lab=lab)
    payload = {
        "action": "save_close",
        "idempotency_key": "ordinary-idempotent-1",
        "configuration_fingerprint": session.configuration_fingerprint,
        "observations": {
            task.uuid: {
                "disease_grading_id": label.id,
                "selected_feature_ids": [],
                "feature_geometry": None,
                "annotation_policy_revision": 1,
            }
        },
    }

    first = submit(
        db_session,
        session_uuid=session.uuid,
        user_id=user.id,
        raw_token=token,
        token_generation=1,
        payload=payload,
    )
    replay = submit(
        db_session,
        session_uuid=session.uuid,
        user_id=user.id,
        raw_token="ignored-after-commit",
        token_generation=1,
        payload=payload,
    )

    assert replay == {
        "event_uuid": first["event_uuid"],
        "idempotent_replay": True,
        "queue_request": session.queue_request_json,
    }
    assert db_session.query(GradingSubmissionEvent).filter_by(session_id=session.id).count() == 1


def test_rejected_submission_audit_does_not_store_observation_payload(
    db_session,
    resident_user,
    core_test_data,
):
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    lab = db_session.merge(core_test_data["lab_unit"])
    _task, session, _token = _leased_encounter_task(
        db_session, user=user, disease=disease, lab=lab
    )

    event = record_rejected_submission(
        db_session,
        actor_user_id=user.id,
        session_uuid=session.uuid,
        result_code="configuration_changed",
        action="save_next",
    )

    assert event.outcome == "conflict"
    assert event.items == []
    assert event.diagnostic_metadata_json == {
        "session_uuid": session.uuid,
        "action": "save_next",
    }


def test_workbench_state_machine_owns_match_consensus(
    db_session,
    resident_user,
    core_test_data,
    disease_grading_glaucoma_normal,
):
    user = db_session.merge(resident_user)
    disease = db_session.merge(core_test_data["glaucoma"])
    lab = db_session.merge(core_test_data["lab_unit"])
    label = db_session.merge(disease_grading_glaucoma_normal)
    task, _session, _token = _leased_encounter_task(
        db_session, user=user, disease=disease, lab=lab
    )
    db_session.add_all([
        Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot="resident",
            disease_grading_id=label.id,
        ),
        Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot="resident2",
            disease_grading_id=label.id,
        ),
    ])
    db_session.flush()

    apply_grade_state(db_session, task=task)

    consensus = db_session.query(Consensus).filter_by(task_id=task.id).one()
    assert task.state == "final"
    assert consensus.method == "match"
    assert consensus.final_disease_grading_id == label.id
