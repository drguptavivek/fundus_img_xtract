from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .models import ReviewSubmissionHistory


class StaleReviewSubmissionError(RuntimeError):
    """The submitted form was based on an older database version."""


class InvalidReviewSubmissionToken(ValueError):
    """The one-time review submission token is invalid or reused out of scope."""


def normalize_submission_request_id(value: str | None) -> str:
    """Return a canonical UUID4 request id supplied by the rendered review form."""
    try:
        parsed = UUID(str(value or ""))
    except (ValueError, AttributeError) as exc:
        raise InvalidReviewSubmissionToken("Invalid review submission token.") from exc
    if parsed.version != 4:
        raise InvalidReviewSubmissionToken("Invalid review submission token.")
    return str(parsed)


def find_submission_history(
    db: Session,
    *,
    request_id: str,
    task_id: int,
    actor_user_id: int,
) -> ReviewSubmissionHistory | None:
    """Find an idempotent replay, rejecting a token reused by another scope."""
    row = (
        db.query(ReviewSubmissionHistory)
        .filter(ReviewSubmissionHistory.request_id == request_id)
        .first()
    )
    if row is None:
        return None
    if row.task_id != task_id or row.actor_user_id != actor_user_id:
        raise InvalidReviewSubmissionToken("Invalid review submission token.")
    return row


def version_token(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def assert_version_token(*, label: str, expected: str | None, current: datetime | None) -> None:
    if current is None:
        matches = expected == ""
    else:
        try:
            submitted = datetime.fromisoformat(expected or "")
            current_value = current if current.tzinfo else current.replace(tzinfo=timezone.utc)
            if submitted.tzinfo is None:
                matches = False
            else:
                matches = submitted.astimezone(timezone.utc) == current_value.astimezone(timezone.utc)
        except ValueError:
            matches = False
    if not matches:
        raise StaleReviewSubmissionError(
            f"{label} changed after this page was loaded. Reload and review the latest values."
        )


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return version_token(value)
    return value


def _snapshot(entity: object | None) -> dict[str, Any] | None:
    if entity is None:
        return None
    return {
        column.key: _json_value(getattr(entity, column.key))
        for column in inspect(entity).mapper.column_attrs
    }


def snapshot_grade(grade: object | None) -> dict[str, Any] | None:
    return _snapshot(grade)


def snapshot_consensus(consensus: object | None) -> dict[str, Any] | None:
    return _snapshot(consensus)


def record_submission_history(
    db: Session,
    *,
    task_id: int,
    actor_user_id: int,
    action_type: str,
    before: dict[str, Any],
    after: dict[str, Any],
    version_tokens: dict[str, Any],
    request_id: str | None = None,
) -> ReviewSubmissionHistory:
    row = ReviewSubmissionHistory(
        request_id=(
            normalize_submission_request_id(request_id)
            if request_id is not None
            else str(uuid4())
        ),
        task_id=task_id,
        actor_user_id=actor_user_id,
        action_type=action_type,
        source="review_task_details",
        before_json=before,
        after_json=after,
        version_tokens_json=version_tokens,
    )
    db.add(row)
    return row
