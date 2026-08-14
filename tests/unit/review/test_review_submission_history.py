from datetime import datetime, timezone
from uuid import uuid4

import pytest

from review_history import (
    InvalidReviewSubmissionToken,
    StaleReviewSubmissionError,
    assert_version_token,
    find_submission_history,
    normalize_submission_request_id,
    record_submission_history,
    version_token,
)
from review_history.models import ReviewSubmissionHistory
from utils.mvw_image_listing_v2 import _build_mv_sql


def test_version_token_rejects_stale_timestamp():
    current = datetime(2026, 8, 8, 6, 0, tzinfo=timezone.utc)

    with pytest.raises(StaleReviewSubmissionError):
        assert_version_token(
            label="Consensus",
            expected="2026-08-08T05:59:59+00:00",
            current=current,
        )


def test_version_token_accepts_exact_utc_value_and_empty_none():
    current = datetime(2026, 8, 8, 6, 0, tzinfo=timezone.utc)

    assert_version_token(label="Consensus", expected=version_token(current), current=current)
    assert_version_token(
        label="Consensus",
        expected="2026-08-08T11:30:00+05:30",
        current=current,
    )
    assert_version_token(label="New review", expected="", current=None)


def test_image_listing_uses_updated_at_for_last_review_wins():
    sql = _build_mv_sql("mvw_image_listing_test_1_v2", 1, "Test")

    assert (
        "ORDER BY g.task_id, g.role_slot, "
        "COALESCE(g.updated_at, g.created_at) DESC, g.id DESC"
    ) in sql


def test_history_record_is_persisted_in_submission_transaction(db_session):
    request_id = str(uuid4())
    record_submission_history(
        db_session,
        task_id=991,
        actor_user_id=17,
        action_type="human_review",
        before={"review_grade": None},
        after={"review_grade": {"id": 123}},
        version_tokens={"consensus_decided_at": ""},
        request_id=request_id,
    )
    db_session.flush()

    row = db_session.query(ReviewSubmissionHistory).one()
    assert row.task_id == 991
    assert row.actor_user_id == 17
    assert row.request_id == request_id
    assert row.before_json == {"review_grade": None}
    assert row.after_json == {"review_grade": {"id": 123}}


def test_submission_request_id_requires_uuid4():
    request_id = str(uuid4())

    assert normalize_submission_request_id(request_id.upper()) == request_id
    with pytest.raises(InvalidReviewSubmissionToken):
        normalize_submission_request_id("")
    with pytest.raises(InvalidReviewSubmissionToken):
        normalize_submission_request_id("not-a-token")


def test_submission_history_replay_is_scoped_to_task_and_actor(db_session):
    request_id = str(uuid4())
    record_submission_history(
        db_session,
        task_id=991,
        actor_user_id=17,
        action_type="human_review",
        before={"review_grade": None},
        after={"review_grade": {"id": 123}},
        version_tokens={},
        request_id=request_id,
    )
    db_session.flush()

    assert find_submission_history(
        db_session,
        request_id=request_id,
        task_id=991,
        actor_user_id=17,
    ) is not None
    with pytest.raises(InvalidReviewSubmissionToken):
        find_submission_history(
            db_session,
            request_id=request_id,
            task_id=992,
            actor_user_id=17,
        )
