"""Reviewer-owned discrepancy-review history queries and DTOs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from encounter_sets.permissions import (
    CAPABILITY_DISCREPANCY_REVIEW,
    apply_task_capability_scope,
)
from models import Disease, DiseaseGrading, Grade, GradingTask, Hospital, LabUnit, User
from utils.timezone_choices import DEFAULT_TIMEZONE


@dataclass(frozen=True)
class MyDiscrepancyReviewDTO:
    task_id: int
    task_state: str
    disease_id: int
    disease_name: str
    grade_impression: str
    comment: str | None
    lab_unit_name: str
    hospital_name: str
    reviewed_at: datetime

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["reviewed_at"] = self.reviewed_at.isoformat()
        return data


@dataclass(frozen=True)
class MyDiscrepancyReviewPageDTO:
    items: tuple[MyDiscrepancyReviewDTO, ...]
    diseases: tuple[dict[str, object], ...]
    date_from: str | None
    date_to: str | None
    disease_id: int | None
    page: int
    per_page: int
    total_count: int
    total_pages: int

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    def to_dict(self) -> dict[str, object]:
        return {
            "items": [item.to_dict() for item in self.items],
            "filters": {
                "date_from": self.date_from,
                "date_to": self.date_to,
                "disease_id": self.disease_id,
                "diseases": list(self.diseases),
            },
            "pagination": {
                "page": self.page,
                "per_page": self.per_page,
                "total_count": self.total_count,
                "total_pages": self.total_pages,
                "has_previous": self.has_previous,
                "has_next": self.has_next,
            },
        }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc


def _user_timezone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _utc_day_bounds(day: date, timezone_info: ZoneInfo) -> tuple[datetime, datetime]:
    local_start = datetime.combine(day, time.min, tzinfo=timezone_info)
    local_end = datetime.combine(date.fromordinal(day.toordinal() + 1), time.min, tzinfo=timezone_info)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _base_query(db: Session, *, user: User):
    reviewed_at = func.coalesce(Grade.updated_at, Grade.created_at)
    query = (
        db.query(
            Grade.task_id.label("task_id"),
            GradingTask.state.label("task_state"),
            Disease.id.label("disease_id"),
            Disease.name.label("disease_name"),
            DiseaseGrading.impression.label("grade_impression"),
            Grade.comment.label("comment"),
            LabUnit.name.label("lab_unit_name"),
            Hospital.name.label("hospital_name"),
            reviewed_at.label("reviewed_at"),
            Grade.id.label("grade_id"),
        )
        .join(GradingTask, GradingTask.id == Grade.task_id)
        .join(Disease, Disease.id == GradingTask.disease_id)
        .join(DiseaseGrading, DiseaseGrading.id == Grade.disease_grading_id)
        .join(LabUnit, LabUnit.id == GradingTask.lab_unit_id)
        .join(Hospital, Hospital.id == LabUnit.hospital_id)
        .filter(
            Grade.grader_user_id == user.id,
            Grade.role_slot == "review",
        )
    )
    return apply_task_capability_scope(
        query,
        GradingTask,
        user,
        CAPABILITY_DISCREPANCY_REVIEW,
    )


def my_discrepancy_review_page(
    db: Session,
    *,
    user: User,
    requested_date_from: str | None,
    requested_date_to: str | None,
    disease_id: int | None,
    page: int,
    per_page: int,
) -> MyDiscrepancyReviewPageDTO:
    """Return the caller's current review-grade history in their active scope."""
    selected_from = _parse_date(requested_date_from)
    selected_to = _parse_date(requested_date_to)
    if selected_from and selected_to and selected_to < selected_from:
        raise ValueError("End date must be on or after start date.")
    page = max(1, page)
    per_page = min(100, max(1, per_page))

    base_query = _base_query(db, user=user)
    disease_rows = (
        base_query.with_entities(Disease.id, Disease.name)
        .distinct()
        .order_by(Disease.name, Disease.id)
        .all()
    )
    diseases = tuple({"id": row.id, "name": row.name} for row in disease_rows)
    allowed_disease_ids = {int(item["id"]) for item in diseases}
    if disease_id is not None and disease_id not in allowed_disease_ids:
        raise ValueError("Disease is unavailable in your discrepancy-review history.")

    filtered_query = base_query
    if disease_id is not None:
        filtered_query = filtered_query.filter(GradingTask.disease_id == disease_id)
    if selected_from is not None or selected_to is not None:
        timezone_info = _user_timezone(user)
        reviewed_at = func.coalesce(Grade.updated_at, Grade.created_at)
        if selected_from is not None:
            start_at, _ = _utc_day_bounds(selected_from, timezone_info)
            filtered_query = filtered_query.filter(reviewed_at >= start_at)
        if selected_to is not None:
            _, end_at = _utc_day_bounds(selected_to, timezone_info)
            filtered_query = filtered_query.filter(reviewed_at < end_at)

    total_count = filtered_query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    rows = (
        filtered_query.order_by(
            func.coalesce(Grade.updated_at, Grade.created_at).desc(),
            Grade.id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    items = tuple(
        MyDiscrepancyReviewDTO(
            task_id=row.task_id,
            task_state=row.task_state,
            disease_id=row.disease_id,
            disease_name=row.disease_name,
            grade_impression=row.grade_impression,
            comment=row.comment,
            lab_unit_name=row.lab_unit_name,
            hospital_name=row.hospital_name,
            reviewed_at=row.reviewed_at,
        )
        for row in rows
    )
    return MyDiscrepancyReviewPageDTO(
        items=items,
        diseases=diseases,
        date_from=selected_from.isoformat() if selected_from else None,
        date_to=selected_to.isoformat() if selected_to else None,
        disease_id=disease_id,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
    )
