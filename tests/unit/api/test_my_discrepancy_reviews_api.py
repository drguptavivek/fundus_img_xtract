from datetime import datetime, timezone

from review.my_discrepancy_reviews import (
    MyDiscrepancyReviewDTO,
    MyDiscrepancyReviewPageDTO,
)
from tests.helpers.factories import UserFactory


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _history() -> MyDiscrepancyReviewPageDTO:
    return MyDiscrepancyReviewPageDTO(
        items=(MyDiscrepancyReviewDTO(
            task_id=42,
            task_state="final",
            disease_id=2,
            disease_name="Glaucoma",
            review_type="human_grade",
            review_value="Referable",
            grade_impression="Referable",
            comment="Reviewed",
            ai_model_name=None,
            ai_model_version=None,
            lab_unit_name="Lab A1",
            hospital_name="Hospital A",
            reviewed_at=datetime(2026, 8, 14, 6, 30, tzinfo=timezone.utc),
        ),),
        diseases=({"id": 2, "name": "Glaucoma"},),
        date_from="2026-08-01",
        date_to="2026-08-14",
        disease_id=2,
        page=1,
        per_page=20,
        total_count=1,
        total_pages=1,
    )


def test_my_discrepancy_reviews_api_uses_shared_history_service(
    client, db_session, core_test_data, monkeypatch
):
    lab = db_session.merge(core_test_data["lab_unit"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="my-review-api-user",
        lab_units=[lab],
    )
    _authenticate(client, reviewer)
    captured = {}

    def fake_history(db, **kwargs):
        captured.update(kwargs)
        return _history()

    monkeypatch.setattr(
        "api.my_discrepancy_reviews.my_discrepancy_review_page",
        fake_history,
    )
    response = client.get(
        "/api/review/me/discrepancy-reviews?date_from=2026-08-01&date_to=2026-08-14&disease_id=2"
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["items"][0]["task_id"] == 42
    assert payload["pagination"]["total_count"] == 1
    assert captured["user"].id == reviewer.id
    assert captured["requested_date_from"] == "2026-08-01"
    assert captured["requested_date_to"] == "2026-08-14"
    assert captured["disease_id"] == 2


def test_my_discrepancy_reviews_page_renders_canonical_surface(
    client, db_session, core_test_data, monkeypatch
):
    lab = db_session.merge(core_test_data["lab_unit"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="my-review-page-user",
        lab_units=[lab],
    )
    _authenticate(client, reviewer)
    monkeypatch.setattr(
        "review.task_review.my_discrepancy_review_page",
        lambda db, **kwargs: _history(),
    )

    response = client.get("/review/my-discrepancy-reviews")

    assert response.status_code == 200
    assert b"My Discrepancy Reviews" in response.data
    assert b"my-review-page-user" in response.data
    assert b"View or update" in response.data
    assert b"/review/my-reviews" not in response.data


def test_legacy_my_reviews_route_is_removed(client, db_session, core_test_data):
    lab = db_session.merge(core_test_data["lab_unit"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="removed-my-reviews-route-user",
        lab_units=[lab],
    )
    _authenticate(client, reviewer)

    response = client.get("/review/my-reviews")

    assert response.status_code == 404
