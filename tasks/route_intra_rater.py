"""Routes for intra-rater task management."""

from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Iterable, Sequence

from flask import Response, jsonify, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import (
    DiseaseGrading,
    IntraRaterBatch,
    IntraRaterTask,
    LabUnit,
    UserDiseaseUnitRole,
)
from services.intra_rater_service import (
    BatchCreateParams,
    IntraRaterService,
    SubmitGradeParams,
)
from flask_wtf.csrf import generate_csrf

from . import bp


def _json_error(message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> Response:
    return jsonify({"error": message}), status.value


@bp.route("/intra-rater/batches", methods=["GET"])
@roles_required("admin", "data_manager")
def list_intra_rater_batches() -> Response:
    """Return paginated intra-rater batches as JSON."""
    page = max(1, request.args.get("page", default=1, type=int))
    per_page = min(max(1, request.args.get("per_page", default=25, type=int)), 200)

    with get_db_session() as db:
        query = (
            db.query(IntraRaterBatch)
            .order_by(IntraRaterBatch.created_at.desc(), IntraRaterBatch.id.desc())
        )

        total = query.count()
        batches = query.offset((page - 1) * per_page).limit(per_page).all()

        payload = {
            "page": page,
            "per_page": per_page,
            "total": total,
            "items": [_batch_to_payload(batch) for batch in batches],
        }
        return jsonify(payload)


@bp.route("/intra-rater/batches", methods=["POST"])
@roles_required("admin", "data_manager")
def create_intra_rater_batch() -> Response:
    """
    Create a new intra-rater batch for the specified disease, graders, and options.
    Expects JSON payload validated against scoping constraints.
    """
    data = request.get_json(silent=True) or {}

    try:
        params = _parse_create_payload(data)
    except ValueError as exc:
        return _json_error(str(exc))

    with get_db_session() as db:
        try:
            if params.lab_unit_id is not None:
                _ensure_lab_unit_exists(db, params.lab_unit_id)
            _ensure_graders_authorized(
                db=db,
                grader_ids=params.grader_ids,
                disease_id=params.disease_id,
                lab_unit_id=params.lab_unit_id,
            )
            if params.normal_grade_id is not None:
                _ensure_normal_grade_valid(db, params.disease_id, params.normal_grade_id)
            service = IntraRaterService(db)
            batch = service.create_batch(params)
        except ValueError as exc:  # from validation
            return _json_error(str(exc))

        response = {
            "batch": _batch_to_payload(batch),
        }
        return jsonify(response), HTTPStatus.CREATED.value


@bp.route("/intra-rater/my-tasks", methods=["GET"])
@roles_required("ophthalmologist", "admin", "data_manager")
def list_my_intra_rater_tasks() -> Response:
    """Return intra-rater tasks assigned to the current grader."""
    include_completed = request.args.get("include_completed", default=0, type=int) == 1

    with get_db_session() as db:
        service = IntraRaterService(db)
        tasks = service.list_grader_tasks(
            grader_user_id=current_user.id,
            include_completed=include_completed,
        )
        gradings_map = _load_gradings_map(db, tasks)
        csrf_token = generate_csrf()
        payload = [_task_to_payload(task, gradings_map, csrf_token) for task in tasks]
        return jsonify({"items": payload, "include_completed": include_completed})


@bp.route("/intra-rater/tasks/<int:task_id>/submit", methods=["POST"])
@roles_required("ophthalmologist")
def submit_intra_rater_grade(task_id: int) -> Response:
    """Submit an intra-rater grade for the current grader."""
    data = request.get_json(silent=True) or {}
    try:
        params = _parse_submit_payload(task_id, data)
    except ValueError as exc:
        return _json_error(str(exc))

    with get_db_session() as db:
        service = IntraRaterService(db)
        try:
            grade = service.submit_grade(params)
        except ValueError as exc:
            return _json_error(str(exc))

        response = {
            "grade_id": grade.id,
            "task_id": grade.task_id,
            "batch_id": grade.batch_id,
            "task_state": grade.task.state if grade.task else "completed",
            "created_at": grade.created_at.isoformat() if grade.created_at else None,
        }
        return jsonify(response), HTTPStatus.CREATED.value


def _parse_create_payload(payload: dict) -> BatchCreateParams:
    """Validate and coerce incoming payload into BatchCreateParams."""
    disease_id = _require_positive_int(payload.get("disease_id"), "disease_id")
    grader_ids_raw = payload.get("grader_ids")
    if not isinstance(grader_ids_raw, Iterable):
        raise ValueError("grader_ids must be a list of user IDs")

    grader_ids: list[int] = []
    for raw in grader_ids_raw:
        try:
            coerced = int(raw)
        except (TypeError, ValueError):
            raise ValueError("grader_ids must contain positive integers")
        if coerced <= 0:
            raise ValueError("grader_ids must contain positive integers")
        if coerced not in grader_ids:
            grader_ids.append(coerced)
    if not grader_ids:
        raise ValueError("grader_ids cannot be empty")

    target_images_per_grader = _require_positive_int(
        payload.get("target_images_per_grader"), "target_images_per_grader"
    )

    lab_unit_id = _optional_positive_int(payload.get("lab_unit_id"), "lab_unit_id")
    cooldown_days_override = _optional_positive_int(
        payload.get("cooldown_days_override"), "cooldown_days_override"
    )
    normal_grade_id = _optional_positive_int(payload.get("normal_grade_id"), "normal_grade_id")

    remarks = payload.get("remarks")
    if remarks is not None and not isinstance(remarks, str):
        raise ValueError("remarks must be a string if provided")

    created_by_user_id = current_user.id

    return BatchCreateParams(
        disease_id=disease_id,
        grader_ids=grader_ids,
        target_images_per_grader=target_images_per_grader,
        created_by_user_id=created_by_user_id,
        lab_unit_id=lab_unit_id,
        cooldown_days_override=cooldown_days_override,
        normal_grade_id=normal_grade_id,
        remarks=remarks,
    )


def _parse_submit_payload(task_id: int, payload: dict) -> SubmitGradeParams:
    """Validate grader submission payload."""
    disease_grading_id = _require_positive_int(
        payload.get("disease_grading_id"),
        "disease_grading_id",
    )

    comment = payload.get("comment")
    if comment is not None and not isinstance(comment, str):
        raise ValueError("comment must be a string")

    time_taken = _optional_float(payload.get("time_taken"), "time_taken")
    if time_taken is not None and time_taken < 0:
        raise ValueError("time_taken cannot be negative")

    start_time_raw = payload.get("start_time")
    start_time = None
    if start_time_raw:
        try:
            start_time = datetime.fromisoformat(start_time_raw)
        except ValueError as exc:
            raise ValueError("start_time must be an ISO-8601 timestamp") from exc
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)

    return SubmitGradeParams(
        task_id=task_id,
        grader_user_id=current_user.id,
        disease_grading_id=disease_grading_id,
        comment=comment,
        time_taken=time_taken,
        start_time=start_time,
    )


def _task_to_payload(
    task: IntraRaterTask,
    gradings_map: dict[int, list[DiseaseGrading]] | None = None,
    csrf_token: str | None = None,
) -> dict:
    batch = task.batch
    disease = task.disease
    lab_unit = task.lab_unit
    gradings = (gradings_map or {}).get(task.disease_id, [])
    return {
        "id": task.id,
        "batch_id": task.batch_id,
        "grader_user_id": task.grader_user_id,
        "disease_id": task.disease_id,
        "disease_name": disease.name if disease else None,
        "lab_unit_id": task.lab_unit_id,
        "lab_unit_name": lab_unit.name if lab_unit else None,
        "encounter_file_id": task.encounter_file_id,
        "direct_image_upload_id": task.direct_image_upload_id,
        "source_task_id": task.source_task_id,
        "state": task.state,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "submit_url": url_for("tasks.submit_intra_rater_grade", task_id=task.id),
        "csrf_token": csrf_token,
        "disease_gradings": [
            {"id": grading.id, "impression": grading.impression}
            for grading in gradings
        ],
        "grade_name": task.grades[0].grade_name if task.grades else None,
        "comment": task.grades[0].comment if task.grades else None,
        "graded_at": task.grades[0].created_at.isoformat() if task.grades and task.grades[0].created_at else None,
        "batch": {
            "id": batch.id if batch else None,
            "normal_grade_id": batch.normal_grade_id if batch else None,
        },
    }


def _batch_to_payload(batch: IntraRaterBatch) -> dict:
    return {
        "id": batch.id,
        "disease_id": batch.disease_id,
        "lab_unit_id": batch.lab_unit_id,
        "created_by_user_id": batch.created_by_user_id,
        "cooldown_days_override": batch.cooldown_days_override,
        "target_images_per_grader": batch.target_images_per_grader,
        "normal_grade_id": batch.normal_grade_id,
        "remarks": batch.remarks,
        "selection_snapshot_json": batch.selection_snapshot_json,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
    }


def _require_positive_int(value: object, field: str) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a positive integer")
    if coerced <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return coerced


def _optional_positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    coerced = _require_positive_int(value, field)
    return coerced


def _optional_float(value: object, field: str) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc


def _ensure_lab_unit_exists(db: Session, lab_unit_id: int) -> None:
    exists_query = (
        db.query(LabUnit.id)
        .filter(LabUnit.id == lab_unit_id)
        .exists()
    )
    if not db.query(exists_query).scalar():
        raise ValueError(f"Lab unit {lab_unit_id} not found")


def _ensure_graders_authorized(
    *,
    db: Session,
    grader_ids: Sequence[int],
    disease_id: int,
    lab_unit_id: int | None,
) -> None:
    """Ensure all graders have active permissions for disease/lab."""
    if not grader_ids:
        raise ValueError("grader_ids cannot be empty")

    q = db.query(UserDiseaseUnitRole.user_id).filter(
        UserDiseaseUnitRole.user_id.in_(grader_ids),
        UserDiseaseUnitRole.disease_id == disease_id,
        UserDiseaseUnitRole.active.is_(True),
        or_(
            UserDiseaseUnitRole.can_grade_resident.is_(True),
            UserDiseaseUnitRole.can_grade_faculty.is_(True),
            UserDiseaseUnitRole.can_arbitrate.is_(True),
        ),
    )
    if lab_unit_id is not None:
        q = q.filter(UserDiseaseUnitRole.lab_unit_id == lab_unit_id)

    eligible_ids = {user_id for (user_id,) in q.distinct()}
    missing = set(grader_ids) - eligible_ids
    if missing:
        raise ValueError(f"Graders lack permissions for disease/lab unit: {sorted(missing)}")


def _ensure_normal_grade_valid(db: Session, disease_id: int, normal_grade_id: int) -> None:
    """Validate that chosen normal grade belongs to disease and is active."""
    exists_query = (
        db.query(DiseaseGrading.id)
        .filter(
            DiseaseGrading.id == normal_grade_id,
            DiseaseGrading.disease_id == disease_id,
            DiseaseGrading.is_active.is_(True),
        )
        .exists()
    )
    if not db.query(exists_query).scalar():
        raise ValueError("normal_grade_id must reference an active grading for the disease")


def _load_gradings_map(db: Session, tasks: Sequence[IntraRaterTask]) -> dict[int, list[DiseaseGrading]]:
    disease_ids = {task.disease_id for task in tasks if task.disease_id}
    gradings_map: dict[int, list[DiseaseGrading]] = {}
    if not disease_ids:
        return gradings_map

    gradings = (
        db.query(DiseaseGrading)
        .filter(DiseaseGrading.disease_id.in_(disease_ids), DiseaseGrading.is_active.is_(True))
        .order_by(DiseaseGrading.display_order.asc(), DiseaseGrading.impression.asc())
        .all()
    )
    for grading in gradings:
        gradings_map.setdefault(grading.disease_id, []).append(grading)
    return gradings_map
@bp.route("/intra-rater", methods=["GET"])
@roles_required("ophthalmologist", "admin", "data_manager")
def intra_rater_dashboard() -> str:
    """Render the intra-rater task dashboard for the logged-in grader."""
    with get_db_session() as db:
        service = IntraRaterService(db)
        tasks = service.list_grader_tasks(grader_user_id=current_user.id, include_completed=False)

        gradings_map = _load_gradings_map(db, tasks)

        return render_template(
            "tasks/intra_rater/queue.html",
            tasks=tasks,
            gradings_map=gradings_map,
            include_completed=False,
        )
