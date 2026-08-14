from datetime import datetime, timezone

import pytest

from models import DiseaseGrading, Grade, GradingTask
from review.my_discrepancy_reviews import my_discrepancy_review_page
from tests.helpers.factories import ImageFactory, UserFactory


def _review_grade(db_session, *, reviewer, lab, disease, hospital, impression, reviewed_at):
    label = (
        db_session.query(DiseaseGrading)
        .filter(DiseaseGrading.disease_id == disease.id)
        .first()
    )
    if label is None:
        label = DiseaseGrading(
            disease_id=disease.id,
            impression=impression,
            guidelines="Test review grade",
            is_active=True,
        )
        db_session.add(label)
        db_session.flush()
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=hospital.id,
        lab_unit_id=lab.id,
        user_id=reviewer.id,
        disease_id=disease.id,
    )
    task = GradingTask(
        direct_image_upload_id=image.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="final",
    )
    db_session.add(task)
    db_session.flush()
    grade = Grade(
        task_id=task.id,
        grader_user_id=reviewer.id,
        role_slot="review",
        disease_grading_id=label.id,
        grade_name=label.impression,
        disease_name=disease.name,
        comment="Reviewed by me",
        created_at=reviewed_at,
        updated_at=reviewed_at,
    )
    db_session.add(grade)
    db_session.flush()
    return task


def test_my_discrepancy_reviews_are_owner_scoped_and_filter_by_local_date(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_unit"])
    hospital = db_session.merge(core_test_data["hospital"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="my-review-history-user",
        lab_units=[lab],
    )
    reviewer.timezone = "Asia/Kolkata"
    reviewed_at = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)
    task = _review_grade(
        db_session,
        reviewer=reviewer,
        lab=lab,
        disease=glaucoma,
        hospital=hospital,
        impression="Reviewed",
        reviewed_at=reviewed_at,
    )

    other_reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="other-review-history-user",
        lab_units=[lab],
    )
    _review_grade(
        db_session,
        reviewer=other_reviewer,
        lab=lab,
        disease=glaucoma,
        hospital=hospital,
        impression="Other",
        reviewed_at=reviewed_at,
    )

    result = my_discrepancy_review_page(
        db_session,
        user=reviewer,
        requested_date_from="2026-08-14",
        requested_date_to="2026-08-14",
        disease_id=glaucoma.id,
        page=1,
        per_page=20,
    )

    assert result.total_count == 1
    assert result.items[0].task_id == task.id
    assert result.items[0].comment == "Reviewed by me"
    assert result.date_from == "2026-08-14"
    assert result.date_to == "2026-08-14"
    assert result.to_dict()["pagination"]["total_count"] == 1


def test_my_discrepancy_reviews_rejects_invalid_date(db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="invalid-review-history-date-user",
        lab_units=[lab],
    )

    with pytest.raises(ValueError, match="Date must use YYYY-MM-DD format"):
        my_discrepancy_review_page(
            db_session,
            user=reviewer,
            requested_date_from="14-08-2026",
            requested_date_to=None,
            disease_id=None,
            page=1,
            per_page=20,
        )


def test_my_discrepancy_reviews_rejects_reversed_date_range(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_unit"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="reversed-review-history-range-user",
        lab_units=[lab],
    )

    with pytest.raises(ValueError, match="End date must be on or after start date"):
        my_discrepancy_review_page(
            db_session,
            user=reviewer,
            requested_date_from="2026-08-14",
            requested_date_to="2026-08-01",
            disease_id=None,
            page=1,
            per_page=20,
        )
