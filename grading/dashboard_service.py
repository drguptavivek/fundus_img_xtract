"""DTO-based eligibility and mixed grading-history reads for the grader dashboard."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import selectinload

from grading_allocation.models import (
    ProjectGraderAllocation,
    ProjectGradingAllocationPolicy,
)
from models import (
    Disease,
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    EncounterSetGradingSubmission,
    EncounterSetGradingSubmissionItem,
    EncounterSetImage,
    Grade,
    GradingTask,
    LabUnit,
    PatientEncounters,
    Project,
    User,
    UserDiseaseUnitRole,
)
from utils.dualGradingRevisionUtils import check_revision_eligibility_by_task_state
from utils.hospital_scoping import apply_scoping
from utils.timezone_choices import DEFAULT_TIMEZONE


HISTORY_TYPES = {"all", "image", "encounter_set"}


@dataclass(frozen=True)
class DailyTrendDTO:
    date: str
    task_count: int
    image_count: int


@dataclass(frozen=True)
class HistoryPageDTO:
    selected_date: str
    requested_date: str | None
    used_latest_fallback: bool
    history_type: str
    disease_id: int | None
    page: int
    per_page: int
    total_cards: int
    total_pages: int
    total_tasks: int
    total_images: int
    previous_date: str | None
    next_date: str | None
    available_diseases: tuple[dict[str, Any], ...]
    trends: tuple[DailyTrendDTO, ...]
    items: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["trends"] = [asdict(item) for item in self.trends]
        result["items"] = list(self.items)
        result["available_diseases"] = list(self.available_diseases)
        return result


def grader_eligibility_dto(db, *, user_id: int) -> dict[str, Any]:
    """Separate legacy/non-project eligibility from effective project allocation."""
    legacy_rows = (
        db.query(UserDiseaseUnitRole)
        .options(
            selectinload(UserDiseaseUnitRole.disease),
            selectinload(UserDiseaseUnitRole.lab_unit).selectinload(LabUnit.hospital),
        )
        .filter(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.active.is_(True),
        )
        .order_by(UserDiseaseUnitRole.lab_unit_id, UserDiseaseUnitRole.disease_id)
        .all()
    )
    non_project = []
    for row in legacy_rows:
        slots = []
        if row.can_grade_resident:
            slots.append("resident")
        if row.can_grade_resident2:
            slots.append("resident2")
        if row.can_arbitrate:
            slots.append("arbitrator")
        if not slots:
            continue
        non_project.append({
            "hospital": {
                "id": row.lab_unit.hospital_id,
                "name": row.lab_unit.hospital.name,
            },
            "lab_unit": {"id": row.lab_unit_id, "name": row.lab_unit.name},
            "disease": {"id": row.disease_id, "name": row.disease.name},
            "role_slots": slots,
        })

    project_rows = (
        db.query(ProjectGraderAllocation, Project, ProjectGradingAllocationPolicy)
        .join(Project, Project.id == ProjectGraderAllocation.project_id)
        .outerjoin(
            ProjectGradingAllocationPolicy,
            ProjectGradingAllocationPolicy.project_id == Project.id,
        )
        .options(
            selectinload(ProjectGraderAllocation.lab_unit).selectinload(LabUnit.hospital),
            selectinload(ProjectGraderAllocation.disease),
            selectinload(ProjectGraderAllocation.encounter_set_type),
        )
        .filter(
            ProjectGraderAllocation.user_id == user_id,
            ProjectGraderAllocation.active.is_(True),
            Project.active.is_(True),
        )
        .order_by(Project.title, ProjectGraderAllocation.id)
        .all()
    )
    project = []
    for allocation, project_row, policy in project_rows:
        project.append({
            "project": {
                "id": project_row.id,
                "title": project_row.title,
                "code": project_row.code,
            },
            "lab_unit": {
                "id": allocation.lab_unit_id,
                "name": allocation.lab_unit.name,
            },
            "scope": allocation.scope,
            "capacity": allocation.capacity,
            "disease": (
                {"id": allocation.disease_id, "name": allocation.disease.name}
                if allocation.disease else None
            ),
            "encounter_set_type": (
                {
                    "id": allocation.encounter_set_type_id,
                    "name": allocation.encounter_set_type.name,
                }
                if allocation.encounter_set_type else None
            ),
            "enforcement_enabled": bool(policy and policy.enforcement_enabled),
            "effective": bool(policy and policy.enforcement_enabled),
        })
    return {"non_project": non_project, "project": project}


def grading_history_page(
    db,
    *,
    user_id: int,
    requested_date: str | None,
    history_type: str,
    disease_id: int | None,
    page: int,
    per_page: int,
) -> HistoryPageDTO:
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("Grader not found.")
    if history_type not in HISTORY_TYPES:
        raise ValueError("History type must be all, image, or encounter_set.")
    requested_day = _parse_date(requested_date) if requested_date else None
    timezone_info = _user_timezone(user)
    today = datetime.now(timezone_info).date()
    available_dates = _available_dates(
        db,
        user=user,
        history_type=history_type,
        disease_id=disease_id,
        timezone_info=timezone_info,
    )
    target_day = requested_day or today
    used_latest_fallback = False
    if target_day not in available_dates and available_dates:
        target_day = available_dates[0]
        used_latest_fallback = True

    record_refs = _day_record_refs(
        db,
        user=user,
        day=target_day,
        history_type=history_type,
        disease_id=disease_id,
        timezone_info=timezone_info,
    )
    total_cards = len(record_refs)
    total_tasks, total_images = _record_ref_totals(db, record_refs)
    total_pages = max(1, (total_cards + per_page - 1) // per_page)
    page = min(max(1, page), total_pages)
    start = (page - 1) * per_page
    page_items = tuple(
        _items_for_record_refs(
            db,
            user=user,
            refs=record_refs[start:start + per_page],
            disease_id=disease_id,
        )
    )

    previous_date = None
    next_date = None
    if target_day in available_dates:
        index = available_dates.index(target_day)
        if index + 1 < len(available_dates):
            previous_date = available_dates[index + 1].isoformat()
        if index > 0:
            next_date = available_dates[index - 1].isoformat()

    trend_days = list(reversed(available_dates[:7]))
    trends = []
    for trend_day in trend_days:
        trend_refs = _day_record_refs(
            db,
            user=user,
            day=trend_day,
            history_type=history_type,
            disease_id=disease_id,
            timezone_info=timezone_info,
        )
        trend_task_count, trend_image_count = _record_ref_totals(db, trend_refs)
        trends.append(DailyTrendDTO(
            date=trend_day.isoformat(),
            task_count=trend_task_count,
            image_count=trend_image_count,
        ))

    return HistoryPageDTO(
        selected_date=target_day.isoformat(),
        requested_date=requested_date,
        used_latest_fallback=used_latest_fallback,
        history_type=history_type,
        disease_id=disease_id,
        page=page,
        per_page=per_page,
        total_cards=total_cards,
        total_pages=total_pages,
        total_tasks=total_tasks,
        total_images=total_images,
        previous_date=previous_date,
        next_date=next_date,
        available_diseases=_available_diseases(db, user=user),
        trends=tuple(trends),
        items=page_items,
    )


def _available_dates(db, *, user, history_type, disease_id, timezone_info):
    timestamps = []
    if history_type in {"all", "encounter_set"}:
        timestamps.extend(
            row[0] for row in _submission_query(
                db, user=user, disease_id=disease_id
            ).with_entities(EncounterSetGradingSubmission.created_at).distinct().all()
        )
    timestamps.extend(
        row[0] for row in _grade_query(
            db,
            user=user,
            history_type=history_type,
            disease_id=disease_id,
        ).with_entities(
            func.coalesce(Grade.updated_at, Grade.created_at)
        ).all()
    )
    return sorted(
        {_aware(value).astimezone(timezone_info).date() for value in timestamps if value},
        reverse=True,
    )


def _day_record_refs(db, *, user, day, history_type, disease_id, timezone_info):
    start, end = _utc_day_bounds(day, timezone_info)
    refs = []
    if history_type in {"all", "encounter_set"}:
        submission_rows = (
            _submission_query(db, user=user, disease_id=disease_id)
            .enable_eagerloads(False)
            .filter(
                EncounterSetGradingSubmission.created_at >= start,
                EncounterSetGradingSubmission.created_at < end,
            )
            .with_entities(
                EncounterSetGradingSubmission.id,
                EncounterSetGradingSubmission.created_at,
            )
            .all()
        )
        refs.extend(("submission", row_id, timestamp) for row_id, timestamp in submission_rows)

    grade_rows = (
        _grade_query(
            db,
            user=user,
            history_type=history_type,
            disease_id=disease_id,
        )
        .enable_eagerloads(False)
        .filter(
            func.coalesce(Grade.updated_at, Grade.created_at) >= start,
            func.coalesce(Grade.updated_at, Grade.created_at) < end,
        )
        .with_entities(
            Grade.id,
            func.coalesce(Grade.updated_at, Grade.created_at),
        )
        .all()
    )
    refs.extend(("grade", row_id, timestamp) for row_id, timestamp in grade_rows)
    return sorted(refs, key=lambda row: (_aware(row[2]), row[1]), reverse=True)


def _record_ref_totals(db, refs):
    submission_ids = [row_id for kind, row_id, _timestamp in refs if kind == "submission"]
    grade_ids = [row_id for kind, row_id, _timestamp in refs if kind == "grade"]
    submission_task_ids = (
        db.query(EncounterSetGradingSubmissionItem.task_id)
        .filter(EncounterSetGradingSubmissionItem.submission_id.in_(submission_ids))
        .all()
        if submission_ids else []
    )
    grade_task_ids = (
        db.query(Grade.task_id).filter(Grade.id.in_(grade_ids)).all()
        if grade_ids else []
    )
    task_ids = {row[0] for row in submission_task_ids + grade_task_ids}
    source_rows = (
        db.query(
            GradingTask.encounter_file_id,
            GradingTask.direct_image_upload_id,
            GradingTask.encounter_set_image_id,
        )
        .filter(GradingTask.id.in_(task_ids))
        .all()
        if task_ids else []
    )
    image_keys = set()
    for encounter_file_id, direct_image_id, encounter_set_image_id in source_rows:
        if encounter_file_id:
            image_keys.add(("encounter_file", encounter_file_id))
        elif direct_image_id:
            image_keys.add(("direct_image", direct_image_id))
        elif encounter_set_image_id:
            image_keys.add(("encounter_set_image", encounter_set_image_id))
    return len(submission_task_ids) + len(grade_ids), len(image_keys)


def _items_for_record_refs(db, *, user, refs, disease_id):
    submission_ids = [row_id for kind, row_id, _timestamp in refs if kind == "submission"]
    grade_ids = [row_id for kind, row_id, _timestamp in refs if kind == "grade"]
    submissions = (
        _submission_query(db, user=user, disease_id=disease_id)
        .filter(EncounterSetGradingSubmission.id.in_(submission_ids))
        .all()
        if submission_ids else []
    )
    task_ids = {
        item.task_id for submission in submissions for item in submission.items
    }
    task_map = {
        task.id: task
        for task in (
            db.query(GradingTask)
            .options(
                selectinload(GradingTask.disease),
                selectinload(GradingTask.encounter_set_image),
            )
            .filter(GradingTask.id.in_(task_ids))
            .all()
            if task_ids else []
        )
    }
    items = [_submission_card(row, task_map) for row in submissions]
    grades = (
        _grade_query(
            db,
            user=user,
            history_type="all",
            disease_id=disease_id,
        )
        .filter(Grade.id.in_(grade_ids))
        .all()
        if grade_ids else []
    )
    items.extend(_grade_card(grade) for grade in grades)
    for item in items:
        item.pop("_image_uuids", None)
    return sorted(items, key=lambda item: (item["timestamp"], item["key"]), reverse=True)


def _submission_query(db, *, user, disease_id):
    query = (
        db.query(EncounterSetGradingSubmission)
        .join(EncounterSetGradingPackage)
        .join(PatientEncounters)
        .options(
            selectinload(EncounterSetGradingSubmission.items),
            selectinload(EncounterSetGradingSubmission.package).selectinload(
                EncounterSetGradingPackage.patient_encounter
            ),
        )
        .filter(EncounterSetGradingSubmission.grader_user_id == user.id)
    )
    query = apply_scoping(query, PatientEncounters, user, "grading")
    if disease_id:
        query = (
            query.join(
                EncounterSetGradingSubmissionItem,
                EncounterSetGradingSubmissionItem.submission_id
                == EncounterSetGradingSubmission.id,
            )
            .join(
                GradingTask,
                GradingTask.id == EncounterSetGradingSubmissionItem.task_id,
            )
            .filter(or_(
                GradingTask.disease_id == disease_id,
                EncounterSetGradingSubmissionItem.scope_disease_id == disease_id,
            ))
            .distinct()
        )
    return query


def _grade_query(db, *, user, history_type, disease_id):
    submitted_grade = select(EncounterSetGradingSubmissionItem.id).where(
        EncounterSetGradingSubmissionItem.grade_id == Grade.id
    ).correlate(Grade)
    query = (
        db.query(Grade)
        .join(GradingTask, Grade.task_id == GradingTask.id)
        .outerjoin(
            EncounterSetGradingScope,
            EncounterSetGradingScope.id == GradingTask.encounter_set_scope_id,
        )
        .options(
            selectinload(Grade.label),
            selectinload(Grade.task).selectinload(GradingTask.disease),
            selectinload(Grade.task).selectinload(GradingTask.lab_unit),
            selectinload(Grade.task).selectinload(GradingTask.encounter_file),
            selectinload(Grade.task).selectinload(GradingTask.direct_image),
            selectinload(Grade.task).selectinload(GradingTask.patient_encounter),
            selectinload(Grade.task).selectinload(GradingTask.encounter_set_image)
            .selectinload(EncounterSetImage.patient_encounter),
            selectinload(Grade.task).selectinload(GradingTask.encounter_set_package)
            .selectinload(EncounterSetGradingPackage.patient_encounter),
            selectinload(Grade.task).selectinload(GradingTask.encounter_set_scope)
            .selectinload(EncounterSetGradingScope.scope_disease),
        )
        .filter(
            Grade.grader_user_id == user.id,
            Grade.role_slot != "review",
            ~exists(submitted_grade),
        )
    )
    query = apply_scoping(query, Grade, user, "grading")
    encounter_predicate = or_(
        GradingTask.encounter_set_package_id.is_not(None),
        GradingTask.encounter_set_image_id.is_not(None),
        GradingTask.patient_encounter_id.is_not(None),
    )
    if history_type == "image":
        query = query.filter(~encounter_predicate)
    elif history_type == "encounter_set":
        query = query.filter(encounter_predicate)
    if disease_id:
        query = query.filter(or_(
            GradingTask.disease_id == disease_id,
            EncounterSetGradingScope.scope_disease_id == disease_id,
        ))
    return query


def _submission_card(submission, task_map):
    package = submission.package
    set_grades = []
    image_grades = []
    disease_map = {}
    image_uuids = set()
    for item in submission.items:
        task = task_map.get(item.task_id)
        target = item.target_snapshot_json or {}
        disease_id = item.scope_disease_id or target.get("disease_id")
        disease_name = item.scope_disease_name or target.get("disease_name") or "Unknown"
        if disease_id:
            disease_map[disease_id] = disease_name
        observation = {
            "disease_id": disease_id,
            "disease_name": disease_name,
            "grade": item.grade_name,
            "comment": item.comment,
        }
        if item.target_level == "encounter":
            set_grades.append(observation)
        else:
            image_uuid = (
                task.encounter_set_image.uuid
                if task and task.encounter_set_image else None
            )
            observation["image_uuid"] = image_uuid
            image_grades.append(observation)
            if image_uuid:
                image_uuids.add(image_uuid)
    return {
        "key": f"submission:{submission.uuid}",
        "record_kind": "submission",
        "type": "encounter_set",
        "type_label": "EncounterSet",
        "scope_label": (
            "Unified set" if package.grading_mode == "unified" else "Disease set"
        ),
        "role_slot": submission.role_slot,
        "timestamp": submission.created_at,
        "is_revision": submission.submission_kind == "revision",
        "submission_kind": submission.submission_kind,
        "uuid": package.patient_encounter.uuid,
        "package_uuid": package.uuid,
        "package_name": package.name,
        "diseases": [
            {"id": disease_id, "name": name}
            for disease_id, name in sorted(disease_map.items(), key=lambda row: row[1])
        ],
        "set_grades": set_grades,
        "image_grades": image_grades,
        "task_count": len(submission.items),
        "image_count": len(image_uuids),
        "_image_uuids": tuple(image_uuids),
    }


def _grade_card(grade):
    task = grade.task
    is_encounter_set = bool(
        task.encounter_set_package_id
        or task.encounter_set_image_id
        or task.patient_encounter_id
    )
    image_uuid = None
    encounter_uuid = None
    if task.encounter_file:
        image_uuid = task.encounter_file.uuid
    elif task.direct_image:
        image_uuid = task.direct_image.uuid
    elif task.encounter_set_image:
        image_uuid = task.encounter_set_image.uuid
        encounter_uuid = task.encounter_set_image.patient_encounter.uuid
    elif task.patient_encounter:
        encounter_uuid = task.patient_encounter.uuid
    if task.encounter_set_package:
        encounter_uuid = task.encounter_set_package.patient_encounter.uuid
    disease = (
        task.encounter_set_scope.scope_disease
        if task.encounter_set_scope and task.encounter_set_scope.scope_disease
        else task.disease
    )
    observation = {
        "disease_id": disease.id,
        "disease_name": disease.name,
        "grade": grade.grade_name or (grade.label.impression if grade.label else None),
        "comment": grade.comment,
    }
    if image_uuid:
        observation["image_uuid"] = image_uuid
    can_revise, _revision_message = check_revision_eligibility_by_task_state(
        task.state,
        grade.role_slot,
        grade.created_at,
    )
    return {
        "key": f"grade:{grade.id}",
        "record_kind": "legacy_grade" if is_encounter_set else "grade",
        "type": "encounter_set" if is_encounter_set else "image",
        "type_label": "EncounterSet" if is_encounter_set else "Image",
        "scope_label": (
            "Set target"
            if is_encounter_set and task.grading_target_level == "encounter"
            else "EncounterSet image"
            if is_encounter_set else "Single image"
        ),
        "role_slot": grade.role_slot,
        "timestamp": grade.updated_at or grade.created_at,
        "is_revision": bool(
            grade.updated_at and grade.created_at
            and (grade.updated_at - grade.created_at).total_seconds() > 1
        ),
        "submission_kind": None,
        "grade_id": grade.id,
        "can_revise": bool(image_uuid) and grade.role_slot != "ai" and can_revise,
        "can_view": bool(image_uuid) and grade.role_slot != "ai",
        "uuid": encounter_uuid if is_encounter_set else image_uuid,
        "package_uuid": task.encounter_set_package.uuid if task.encounter_set_package else None,
        "package_name": task.encounter_set_package.name if task.encounter_set_package else None,
        "diseases": [{"id": disease.id, "name": disease.name}],
        "set_grades": [observation] if task.grading_target_level == "encounter" else [],
        "image_grades": [observation] if task.grading_target_level != "encounter" else [],
        "task_count": 1,
        "image_count": 1 if image_uuid else 0,
        "_image_uuids": (image_uuid,) if image_uuid else (),
    }


def _available_diseases(db, *, user):
    grade_ids = db.execute(
        select(GradingTask.disease_id)
        .join(Grade, Grade.task_id == GradingTask.id)
        .where(Grade.grader_user_id == user.id, Grade.role_slot != "review")
    ).scalars().all()
    scope_ids = db.execute(
        select(EncounterSetGradingSubmissionItem.scope_disease_id)
        .join(EncounterSetGradingSubmission)
        .where(
            EncounterSetGradingSubmission.grader_user_id == user.id,
            EncounterSetGradingSubmissionItem.scope_disease_id.is_not(None),
        )
    ).scalars().all()
    disease_ids = set(grade_ids) | set(scope_ids)
    diseases = (
        db.query(Disease)
        .filter(Disease.id.in_(disease_ids))
        .order_by(Disease.name)
        .all()
        if disease_ids else []
    )
    return tuple({"id": disease.id, "name": disease.name} for disease in diseases)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc


def _user_timezone(user) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _utc_day_bounds(day: date, timezone_info: ZoneInfo):
    local_start = datetime.combine(day, time.min, tzinfo=timezone_info)
    local_end = datetime.combine(day.fromordinal(day.toordinal() + 1), time.min, tzinfo=timezone_info)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
