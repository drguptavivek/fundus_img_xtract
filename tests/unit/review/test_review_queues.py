import pytest
from datetime import date

from models import Consensus, DiseaseGrading, GradingTask, PatientEncounters
from review.queues import ReviewQueueError, create_review_queue, load_review_queue, parse_task_id_csv
from tests.helpers.factories import UserFactory


def test_parse_task_id_csv_deduplicates_in_source_order():
    assert parse_task_id_csv(b"task_id,cohort\n12,a\n7,b\n12,c\n") == (12, 7)


@pytest.mark.parametrize(
    "content,message",
    [
        (b"id\n1\n", "task_id column"),
        (b"task_id\nnot-an-id\n", "Invalid task_id"),
        (b"task_id\n", "contains no task IDs"),
    ],
)
def test_parse_task_id_csv_rejects_invalid_input(content, message):
    with pytest.raises(ReviewQueueError, match=message):
        parse_task_id_csv(content)


def test_create_and_reload_review_queue_preserves_order(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    grading = db_session.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="queue_reviewer",
        lab_units=[lab],
    )
    encounters = [
        PatientEncounters(
            name=f"Queue Patient {index}",
            patient_id=f"QUEUE-{index}",
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
    db_session.add_all([
        Consensus(
            task_id=task.id,
            method="match",
            final_disease_grading_id=grading.id,
        )
        for task in tasks
    ])
    db_session.flush()
    source_order = (tasks[1].id, tasks[0].id)

    queue = create_review_queue(
        db_session,
        user=reviewer,
        filename="study.csv",
        content=("task_id\n" + "\n".join(map(str, source_order))).encode(),
    )
    loaded = load_review_queue(db_session, user=reviewer, token=queue.token)

    assert loaded.task_ids == source_order
    assert loaded.disease_id == disease.id


def test_create_review_queue_rejects_unscoped_task(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    grading = db_session.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="queue_reviewer_without_lab",
        lab_units=[],
    )
    encounter = PatientEncounters(
        name="Unavailable Queue Patient",
        patient_id="QUEUE-UNAVAILABLE",
        capture_date="2026-08-14",
        capture_date_dt=date(2026, 8, 14),
        lab_unit_id=lab.id,
        is_set_based=True,
    )
    db_session.add(encounter)
    db_session.flush()
    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="final",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(Consensus(
        task_id=task.id,
        method="match",
        final_disease_grading_id=grading.id,
    ))
    db_session.flush()

    with pytest.raises(ReviewQueueError, match="unavailable"):
        create_review_queue(
            db_session,
            user=reviewer,
            filename="study.csv",
            content=f"task_id\n{task.id}\n".encode(),
        )
