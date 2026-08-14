from datetime import date
from uuid import uuid4

import pytest

from models import Consensus, DiseaseGrading, Grade, GradingTask, PatientEncounters
from review.queues import ReviewQueueDTO
from review_history.models import ReviewSubmissionHistory
from tests.helpers.factories import UserFactory


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


@pytest.mark.parametrize(
    "action,next_available",
    [("save", True), ("save_next", True), ("save_next", False)],
)
def test_review_save_actions_persist_and_stay_in_uploaded_queue(
    action,
    next_available,
    client,
    db_session,
    core_test_data,
    monkeypatch,
):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    grading = db_session.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username=f"queue_{action}_{int(next_available)}_reviewer",
        lab_units=[lab],
    )
    encounters = [
        PatientEncounters(
            name=f"Review Queue {index}",
            patient_id=f"REVIEW-QUEUE-{action}-{int(next_available)}-{index}",
            capture_date="2026-08-14",
            capture_date_dt=date(2026, 8, 14),
            lab_unit_id=lab.id,
            is_set_based=True,
        )
        for index in range(2)
    ]
    db_session.add_all(encounters)
    db_session.flush()
    tasks = [
        GradingTask(
            patient_encounter_id=encounter.id,
            disease_id=disease.id,
            lab_unit_id=lab.id,
            state="final",
        )
        for encounter in encounters
    ]
    db_session.add_all(tasks)
    db_session.flush()
    consensuses = [
        Consensus(
            task_id=task.id,
            method="match",
            final_disease_grading_id=grading.id,
        )
        for task in tasks
    ]
    db_session.add_all(consensuses)
    db_session.flush()

    queue = ReviewQueueDTO("study-token", disease.id, tuple(task.id for task in tasks))
    current_task = tasks[0] if next_available else tasks[1]
    current_consensus = consensuses[0] if next_available else consensuses[1]
    monkeypatch.setattr("review.task_review.load_review_queue", lambda db, user, token: queue)
    monkeypatch.setattr("review.task_review.get_task_detail", lambda db, task_id: {"id": task_id})
    queued_refreshes = []
    monkeypatch.setattr(
        "review.task_review._queue_review_listing_refresh",
        lambda disease_id: queued_refreshes.append(disease_id),
    )
    _authenticate(client, reviewer)
    return_to = f"/review/discrepancy-review?review_queue={queue.token}&disease_id={disease.id}"

    submission_token = str(uuid4())
    submission_data = {
        "action": action,
        "grading_id": grading.id,
        "comment": "Study review",
        "review_grade_updated_at": "",
        "consensus_decided_at": current_consensus.decided_at.isoformat(),
        "next_task_id": 999999,
        "review_submission_token": submission_token,
    }
    missing_token_response = client.post(
        f"/review/reviewTaskDetails/{current_task.id}",
        query_string={"review_queue": queue.token, "return_to": return_to},
        data={key: value for key, value in submission_data.items() if key != "review_submission_token"},
    )

    assert missing_token_response.status_code == 302
    assert db_session.query(Grade).filter_by(
        task_id=current_task.id,
        grader_user_id=reviewer.id,
        role_slot="review",
    ).count() == 0
    assert queued_refreshes == []

    response = client.post(
        f"/review/reviewTaskDetails/{current_task.id}",
        query_string={"review_queue": queue.token, "return_to": return_to},
        data=submission_data,
    )

    assert response.status_code == 302
    if action == "save_next" and next_available:
        assert f"/review/reviewTaskDetails/{tasks[1].id}" in response.location
        assert "999999" not in response.location
        assert "review_queue=study-token" in response.location
    else:
        assert response.location.endswith(return_to)
    saved = db_session.query(Grade).filter_by(
        task_id=current_task.id,
        grader_user_id=reviewer.id,
        role_slot="review",
    ).one()
    assert saved.disease_grading_id == grading.id
    assert saved.comment == "Study review"
    assert queued_refreshes == [disease.id]

    replay = client.post(
        f"/review/reviewTaskDetails/{current_task.id}",
        query_string={"review_queue": queue.token, "return_to": return_to},
        data=submission_data,
    )

    assert replay.status_code == 302
    assert replay.location == response.location
    assert queued_refreshes == [disease.id]
    history_rows = db_session.query(ReviewSubmissionHistory).filter_by(
        request_id=submission_token,
    ).all()
    assert len(history_rows) == 1
