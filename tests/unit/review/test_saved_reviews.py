from datetime import datetime, timezone
from uuid import uuid4
from flask import render_template
from models import DiseaseGrading, Grade, GradingTask
from review.saved_reviews import list_saved_reviews
from tests.helpers.factories import ImageFactory, UserFactory


def test_saved_reviews_show_other_reviewers_without_edit_controls(app, db_session, core_test_data):
    author = UserFactory.create_admin(db_session, username=f"saved_author_{uuid4().hex[:8]}")
    lab = db_session.merge(core_test_data["lab_unit"])
    images = [ImageFactory.create_direct_upload(
        db_session, hospital_id=lab.hospital_id, lab_unit_id=lab.id,
        user_id=author.id, disease_id=core_test_data["glaucoma"].id,
        camera_id=core_test_data["camera"].id, area_id=core_test_data["area"].id,
    ) for _ in range(2)]
    tasks = [GradingTask(disease_id=core_test_data["glaucoma"].id,
                         direct_image_upload_id=image.id,
                         lab_unit_id=lab.id, state="final") for image in images]
    db_session.add_all(tasks)
    db_session.flush()
    label = db_session.query(DiseaseGrading).filter_by(disease_id=tasks[0].disease_id).first()
    db_session.add_all([Grade(
        task_id=tasks[0].id, grader_user_id=author.id, role_slot="review",
        disease_grading_id=label.id,
        grade_name="Other Retinal", comment="Hypotony Maculopathy\nAI influence: no",
        updated_at=datetime(2026, 5, 6, 11, 29, tzinfo=timezone.utc),
    ), Grade(task_id=tasks[1].id, grader_user_id=author.id, role_slot="review",
             disease_grading_id=label.id,
             grade_name="Normal", comment="Different task")])
    db_session.flush()
    reviews = list_saved_reviews(db_session, task_id=tasks[0].id)
    assert len(reviews) == 1
    assert reviews[0].reviewer == (author.full_name or author.username)
    with app.test_request_context():
        rendered = render_template("review/_saved_reviews.html", saved_reviews=reviews)
    assert "Other Retinal" in rendered
    assert "Hypotony Maculopathy" in rendered
    assert "Different task" not in rendered
    assert "<form" not in rendered
    assert "<input" not in rendered
