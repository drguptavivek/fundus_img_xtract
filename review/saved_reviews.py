"""Read-only review evidence for an already authorized task detail page."""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import joinedload

from models import Grade


@dataclass(frozen=True)
class SavedReview:
    id: int
    reviewer: str
    grade: str
    comment: str | None
    updated_at: datetime | None


def list_saved_reviews(db, *, task_id: int) -> tuple[SavedReview, ...]:
    """Caller must authorize access to this task before requesting its evidence."""
    rows = (
        db.query(Grade)
        .options(joinedload(Grade.grader), joinedload(Grade.label))
        .filter(Grade.task_id == task_id, Grade.role_slot == "review")
        .order_by(Grade.updated_at.desc().nullslast(), Grade.id.desc())
        .all()
    )
    return tuple(SavedReview(
        id=row.id,
        reviewer=(row.grader.full_name or row.grader.username) if row.grader else f"User {row.grader_user_id}",
        grade=row.grade_name or (row.label.impression if row.label else "Unknown"),
        comment=row.comment,
        updated_at=row.updated_at,
    ) for row in rows)
