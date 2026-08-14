import io

from review.queues import ReviewQueueDTO
from tests.helpers.factories import UserFactory


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_review_queue_upload_api_returns_reusable_review_url(
    client, db_session, core_test_data, monkeypatch
):
    lab = db_session.merge(core_test_data["lab_unit"])
    reviewer = UserFactory.create_by_role(
        db_session,
        "discrepancy_reviewer",
        username="review_queue_api_user",
        lab_units=[lab],
    )
    _authenticate(client, reviewer)
    captured = {}

    def fake_create(_db, *, user, filename, content):
        captured.update(user_id=user.id, filename=filename, content=content)
        return ReviewQueueDTO("queue-token", 3, (42, 17))

    monkeypatch.setattr("api.review_queues.create_review_queue", fake_create)
    response = client.post(
        "/api/review/queues",
        data={"file": (io.BytesIO(b"task_id\n42\n17\n"), "study.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["task_count"] == 2
    assert payload["review_url"] == "/review/discrepancy-review?review_queue=queue-token&disease_id=3"
    assert captured == {
        "user_id": reviewer.id,
        "filename": "study.csv",
        "content": b"task_id\n42\n17\n",
    }
