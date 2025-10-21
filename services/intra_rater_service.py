"""Service layer for intra-rater reliability task batches."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from flask import current_app
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from db_transaction_manager import transaction_scope
from models import (
    AppSetting,
    DiseaseGrading,
    Grade,
    GradingTask,
    IntraRaterBatch,
    IntraRaterGrade,
    IntraRaterTask,
    LabUnit,
)


DEFAULT_COOLDOWN_DAYS = 21
STATE_PENDING = "pending"
STATE_COMPLETED = "completed"


@dataclass(slots=True)
class BatchCreateParams:
    """Incoming request to create an intra-rater batch."""

    disease_id: int
    grader_ids: Sequence[int]
    target_images_per_grader: int
    created_by_user_id: int
    lab_unit_id: Optional[int] = None
    cooldown_days_override: Optional[int] = None
    normal_grade_id: Optional[int] = None
    remarks: Optional[str] = None


@dataclass(slots=True)
class SelectionRecord:
    """Single candidate image picked for intra-rater reassessment."""

    grading_task_id: int
    encounter_file_id: Optional[int]
    direct_image_upload_id: Optional[int]
    grade_id: int
    grader_user_id: int
    grade_created_at: datetime
    is_normal: bool


@dataclass(slots=True)
class SelectionOutcome:
    """Aggregated selection data returned to callers."""

    selected: List[SelectionRecord] = field(default_factory=list)
    excluded_reason_counts: dict[str, int] = field(default_factory=dict)

    @property
    def abnormal_count(self) -> int:
        return sum(1 for rec in self.selected if not rec.is_normal)

    @property
    def normal_count(self) -> int:
        return sum(1 for rec in self.selected if rec.is_normal)

    def to_dict(self) -> dict:
        """Serialize selection details for persistence."""
        return {
            "selected": [
                {
                    "grading_task_id": rec.grading_task_id,
                    "encounter_file_id": rec.encounter_file_id,
                    "direct_image_upload_id": rec.direct_image_upload_id,
                    "grade_id": rec.grade_id,
                    "grader_user_id": rec.grader_user_id,
                    "grade_created_at": rec.grade_created_at.isoformat(),
                    "is_normal": rec.is_normal,
                }
                for rec in self.selected
            ],
            "excluded": self.excluded_reason_counts,
            "abnormal_count": self.abnormal_count,
            "normal_count": self.normal_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


@dataclass(slots=True)
class SubmitGradeParams:
    """Parameters for submitting an intra-rater grade."""

    task_id: int
    grader_user_id: int
    disease_grading_id: int
    comment: Optional[str] = None
    time_taken: Optional[float] = None
    start_time: Optional[datetime] = None


class IntraRaterService:
    """Business logic for creating and managing intra-rater tasks."""

    def __init__(self, db: Session):
        self.db = db

    # --- Public API ----------------------------------------------------- #
    def create_batch(self, params: BatchCreateParams) -> IntraRaterBatch:
        """Create a batch and corresponding intra-rater tasks."""
        self._validate_target(params.target_images_per_grader)
        cooldown_days = self._resolve_cooldown_days(params.cooldown_days_override)
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=cooldown_days)

        lab_unit = self._resolve_lab_unit(params.lab_unit_id)
        selection_snapshot: dict[int, SelectionOutcome] = {}
        tasks_to_persist: list[IntraRaterTask] = []

        for grader_id in params.grader_ids:
            outcome = self._select_candidates_for_grader(
                disease_id=params.disease_id,
                grader_id=grader_id,
                lab_unit_id=lab_unit.id if lab_unit else None,
                normal_grade_id=params.normal_grade_id,
                cutoff_dt=cutoff_dt,
                limit=params.target_images_per_grader,
            )
            selection_snapshot[grader_id] = outcome

            for record in outcome.selected:
                task = IntraRaterTask(
                    grader_user_id=record.grader_user_id,
                    disease_id=params.disease_id,
                    lab_unit_id=lab_unit.id if lab_unit else record_lab_unit_id(
                        self.db, record
                    ),
                    encounter_file_id=record.encounter_file_id,
                    direct_image_upload_id=record.direct_image_upload_id,
                    source_task_id=record.grading_task_id,
                    state=STATE_PENDING,
                )
                tasks_to_persist.append(task)

        batch = IntraRaterBatch(
            disease_id=params.disease_id,
            lab_unit_id=lab_unit.id if lab_unit else None,
            created_by_user_id=params.created_by_user_id,
            cooldown_days_override=params.cooldown_days_override,
            target_images_per_grader=params.target_images_per_grader,
            normal_grade_id=params.normal_grade_id,
            selection_snapshot_json=self._snapshot_to_json(selection_snapshot),
            remarks=params.remarks,
        )

        self.db.add(batch)
        self.db.flush()  # Ensure batch.id available

        for task in tasks_to_persist:
            task.batch_id = batch.id
            self.db.add(task)

        return batch

    def list_grader_tasks(self, grader_user_id: int, include_completed: bool = False) -> list[IntraRaterTask]:
        """Return pending (or all) intra-rater tasks for a grader."""
        query = (
            self.db.query(IntraRaterTask)
            .options(
                selectinload(IntraRaterTask.disease),
                selectinload(IntraRaterTask.batch),
                selectinload(IntraRaterTask.lab_unit),
                selectinload(IntraRaterTask.grades),
            )
            .filter(IntraRaterTask.grader_user_id == grader_user_id)
        )
        if not include_completed:
            query = query.filter(IntraRaterTask.state == STATE_PENDING)
        return query.order_by(IntraRaterTask.created_at.asc()).all()

    def submit_grade(self, params: "SubmitGradeParams") -> IntraRaterGrade:
        """Persist grader submission and close the intra-rater task."""
        task = self.db.get(IntraRaterTask, params.task_id)
        if task is None:
            raise ValueError("Task not found")
        if task.grader_user_id != params.grader_user_id:
            raise ValueError("Task is not assigned to the current grader")
        if task.state == STATE_COMPLETED:
            raise ValueError("Task already completed")

        existing_grade = (
            self.db.query(IntraRaterGrade)
            .filter(IntraRaterGrade.task_id == task.id)
            .first()
        )
        if existing_grade:
            raise ValueError("Grade already submitted for this task")

        grading = self.db.get(DiseaseGrading, params.disease_grading_id)
        if grading is None or grading.disease_id != task.disease_id:
            raise ValueError("Invalid disease grading for this task")

        disease_name = task.disease.name if task.disease else None
        grade = IntraRaterGrade(
            task_id=task.id,
            batch_id=task.batch_id,
            grader_user_id=params.grader_user_id,
            disease_grading_id=params.disease_grading_id,
            comment=params.comment,
            time_taken=params.time_taken,
            start_time=params.start_time,
            disease_name=disease_name,
            grade_name=grading.impression,
            grade_description=grading.guidelines,
        )
        self.db.add(grade)

        task.state = STATE_COMPLETED
        task.updated_at = datetime.now(timezone.utc)
        self.db.add(task)

        self.db.flush()

        return grade


    # --- Internal helpers ----------------------------------------------- #

    def _resolve_cooldown_days(self, override_days: Optional[int]) -> int:
        if override_days is not None and override_days > 0:
            return override_days

        setting = self.db.execute(
            select(AppSetting.value).where(AppSetting.key == "INTRA_RATER_DEFAULT_COOLDOWN_DAYS")
        ).scalar_one_or_none()
        if setting is None:
            return DEFAULT_COOLDOWN_DAYS
        try:
            return max(1, int(setting))
        except (TypeError, ValueError):
            current_app.logger.warning(
                "Invalid INTRA_RATER_DEFAULT_COOLDOWN_DAYS value '%s'; falling back to %s",
                setting,
                DEFAULT_COOLDOWN_DAYS,
            )
            return DEFAULT_COOLDOWN_DAYS

    def _resolve_lab_unit(self, lab_unit_id: Optional[int]) -> Optional[LabUnit]:
        if lab_unit_id is None:
            return None
        lab_unit = self.db.get(LabUnit, lab_unit_id)
        if lab_unit is None:
            raise ValueError(f"Lab unit {lab_unit_id} not found")
        return lab_unit

    def _validate_target(self, target: int) -> None:
        if target <= 0:
            raise ValueError("target_images_per_grader must be positive")

    def _select_candidates_for_grader(
        self,
        *,
        disease_id: int,
        grader_id: int,
        lab_unit_id: Optional[int],
        normal_grade_id: Optional[int],
        cutoff_dt: datetime,
        limit: int,
    ) -> SelectionOutcome:
        grade_alias = aliased(Grade)
        task_alias = aliased(GradingTask)
        grading_alias = aliased(DiseaseGrading)
        intra_task_alias = aliased(IntraRaterTask)

        # Base query: historical grades by this grader/disease before cutoff
        query = (
            self.db.query(
                grade_alias.id.label("grade_id"),
                grade_alias.created_at.label("grade_created_at"),
                task_alias.id.label("task_id"),
                task_alias.encounter_file_id,
                task_alias.direct_image_upload_id,
                task_alias.lab_unit_id.label("task_lab_unit_id"),
                grading_alias.id.label("grading_id"),
                grading_alias.impression,
            )
            .join(task_alias, grade_alias.task_id == task_alias.id)
            .join(grading_alias, grade_alias.disease_grading_id == grading_alias.id)
            .filter(
                grade_alias.grader_user_id == grader_id,
                task_alias.disease_id == disease_id,
                grade_alias.created_at <= cutoff_dt,
            )
        )

        if lab_unit_id is not None:
            query = query.filter(task_alias.lab_unit_id == lab_unit_id)

        query = query.filter(
            ~self.db.query(intra_task_alias.id)
            .filter(
                intra_task_alias.grader_user_id == grader_id,
                intra_task_alias.source_task_id == task_alias.id,
                intra_task_alias.state == STATE_PENDING,
            )
            .exists()
        )

        # Order abnormal first: normal determined via normal_grade_id fallback to impression string heuristics
        query = query.order_by(
            self._normal_sort_expression(grading_alias, normal_grade_id),
            grade_alias.created_at.asc(),
        )

        rows = query.limit(limit * 3).all()  # Fetch extra in case of exclusions
        outcome = SelectionOutcome()

        seen_sources: set[tuple[Optional[int], Optional[int]]] = set()
        for row in rows:
            image_key = (row.encounter_file_id, row.direct_image_upload_id)
            if image_key in seen_sources:
                outcome.excluded_reason_counts["duplicate-image"] = (
                    outcome.excluded_reason_counts.get("duplicate-image", 0) + 1
                )
                continue

            if len(outcome.selected) >= limit:
                break

            seen_sources.add(image_key)
            outcome.selected.append(
                SelectionRecord(
                    grading_task_id=row.task_id,
                    encounter_file_id=row.encounter_file_id,
                    direct_image_upload_id=row.direct_image_upload_id,
                    grade_id=row.grade_id,
                    grader_user_id=grader_id,
                    grade_created_at=row.grade_created_at,
                    is_normal=self._is_normal_grade(
                        grading_id=row.grading_id,
                        impression=row.impression,
                        normal_grade_id=normal_grade_id,
                    ),
                )
            )

        return outcome

    def _normal_sort_expression(self, grading_alias: DiseaseGrading, normal_grade_id: Optional[int]):
        """Return SQL expression that sorts abnormal records first."""
        if normal_grade_id:
            return case((grading_alias.id == normal_grade_id, 1), else_=0).asc()
        # Fallback: treat text containing "normal" (case-insensitive) as normal
        return case(
            (func.lower(grading_alias.impression).like("%normal%"), 1),
            else_=0,
        ).asc()

    def _is_normal_grade(
        self,
        *,
        grading_id: int,
        impression: Optional[str],
        normal_grade_id: Optional[int],
    ) -> bool:
        if normal_grade_id:
            return grading_id == normal_grade_id
        if impression is None:
            return False
        return "normal" in impression.lower()

    def _snapshot_to_json(self, snapshot: dict[int, SelectionOutcome]) -> str:
        payload = {str(grader_id): outcome.to_dict() for grader_id, outcome in snapshot.items()}
        return json.dumps(payload)


def record_lab_unit_id(db: Session, record: SelectionRecord) -> int:
    """Resolve lab-unit for selection records when not explicitly provided."""
    task = db.get(GradingTask, record.grading_task_id)
    if not task:
        raise ValueError(f"Grading task {record.grading_task_id} not found")
    return task.lab_unit_id


def get_default_cooldown_days(db: Session) -> int:
    setting = db.execute(
        select(AppSetting.value).where(AppSetting.key == "INTRA_RATER_DEFAULT_COOLDOWN_DAYS")
    ).scalar_one_or_none()
    if setting is None:
        return DEFAULT_COOLDOWN_DAYS
    try:
        return max(1, int(setting))
    except (TypeError, ValueError):
        current_app.logger.warning(
            "Invalid INTRA_RATER_DEFAULT_COOLDOWN_DAYS value '%s'; falling back to %s",
            setting,
            DEFAULT_COOLDOWN_DAYS,
        )
        return DEFAULT_COOLDOWN_DAYS


def create_batch(params: BatchCreateParams) -> IntraRaterBatch:
    """Convenience wrapper using transaction_scope."""
    with transaction_scope() as db:
        service = IntraRaterService(db)
        batch = service.create_batch(params)
        return batch
