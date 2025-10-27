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
    Disease,
    DiseaseGrading,
    Grade,
    Hospital,
    IntraRaterBatch,
    IntraRaterTask,
    LabUnit,
    User,
    UserDiseaseUnitRole,
)
from services.intra_rater_service import (
    BatchCreateParams,
    IntraRaterService,
    SubmitGradeParams,
)
from services.intra_rater_service import get_default_cooldown_days
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
            "items": [_batch_to_payload(batch, include_counts=True) for batch in batches],
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
    page = max(1, request.args.get("page", default=1, type=int))
    per_page = min(max(1, request.args.get("per_page", default=50, type=int)), 200)

    with get_db_session() as db:
        service = IntraRaterService(db)
        # When include_completed is True, we only want completed tasks
        # When include_completed is False, we only want pending tasks
        completed_only = include_completed 
        result = service.list_grader_tasks(
            grader_user_id=current_user.id,
            include_completed=include_completed,
            page=page,
            per_page=per_page,
            completed_only=completed_only
        )
        gradings_map = _load_gradings_map(db, result['tasks'])
        csrf_token = generate_csrf()
        payload = [_task_to_payload(task, gradings_map, csrf_token, db) for task in result['tasks']]
        return jsonify({
            "items": payload,
            "include_completed": include_completed,
            "pagination": {
                "page": result['page'],
                "per_page": result['per_page'],
                "total": result['total'],
                "pages": result['pages']
            }
        })


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
    _require_positive_int(payload.get("hospital_id"), "hospital_id")
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
    db: Session = None,
) -> dict:
    batch = task.batch
    disease = task.disease
    lab_unit = task.lab_unit
    gradings = (gradings_map or {}).get(task.disease_id, [])
    
    # Get grader information
    grader_name = None
    grader_username = None
    if hasattr(task, 'grader') and task.grader:
        grader_name = task.grader.full_name or task.grader.username
        grader_username = task.grader.username
    
    # Get original grade from source task using denormalized data
    # The task already has grades loaded via selectinload, so we can access source task grades
    original_grade = None
    original_grading = None
    original_grader_name = None
    original_grader_username = None
    if task.source_task_id and hasattr(task, 'source_task') and task.source_task:
        # Find the grade from the source task for the same user
        source_grades = [grade for grade in task.source_task.grades if grade.grader_user_id == task.grader_user_id]
        if source_grades:
            original_grade = source_grades[0]  # Take the first/most recent grade
            # Get the disease grading from the gradings_map
            original_grading = next((g for g in gradings_map.get(task.disease_id, []) if g.id == original_grade.disease_grading_id), None)
            # Get original grader info
            if hasattr(task.source_task, 'grader') and task.source_task.grader:
                original_grader_name = task.source_task.grader.full_name or task.source_task.grader.username
                original_grader_username = task.source_task.grader.username
    
    return {
        "id": task.id,
        "uuid": task.uuid,
        "batch_id": task.batch_id,
        "grader_user_id": task.grader_user_id,
        "grader_name": grader_name,
        "grader_username": grader_username,
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
        "original_grade_name": original_grading.impression if original_grading else None,
        "original_grade_id": original_grade.disease_grading_id if original_grade else None,
        "original_comment": original_grade.comment if original_grade else None,
        "original_graded_at": original_grade.created_at.isoformat() if original_grade and original_grade.created_at else None,
        "original_grader_name": original_grader_name,
        "original_grader_username": original_grader_username,
        "batch": _batch_to_payload(batch) if batch else None,
    }


def _batch_to_payload(batch: IntraRaterBatch, include_counts: bool = False) -> dict:
    payload = {
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
    if include_counts:
        tasks = batch.tasks
        payload["image_count"] = len(tasks)
        grader_disease_counts: dict[str, dict[str, int]] = {}
        for task in tasks:
            if not task.grader or not task.disease:
                continue
            grader_name = task.grader.full_name or task.grader.username
            disease_name = task.disease.name
            disease_map = grader_disease_counts.setdefault(grader_name, {})
            disease_map[disease_name] = disease_map.get(disease_name, 0) + 1
        payload["grader_disease_counts"] = grader_disease_counts
        payload["graders"] = sorted(grader_disease_counts.keys())
        payload["disease_name"] = batch.disease.name if batch.disease else None
        payload["lab_unit_name"] = batch.lab_unit.name if batch.lab_unit else None
        payload["creator_name"] = batch.created_by.full_name if batch.created_by else None
        payload["normal_grade_name"] = batch.normal_grade.impression if batch.normal_grade else None
    return payload


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
            UserDiseaseUnitRole.can_grade_resident2.is_(True),
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
    # Get pagination parameters from query string with defaults
    page = max(1, request.args.get("page", default=1, type=int))
    per_page = min(max(1, request.args.get("per_page", default=50, type=int)), 200)  # Changed back to 50 to match API
    
    with get_db_session() as db:
        service = IntraRaterService(db)
        # Only fetch completed tasks, with proper user scoping
        result = service.list_grader_tasks(
            grader_user_id=current_user.id,
            include_completed=True,  # Only completed tasks
            completed_only=True,     # New parameter to ensure only completed tasks
            page=page,
            per_page=per_page
        )

        gradings_map = _load_gradings_map(db, result['tasks'])

        return render_template(
            "tasks/intra_rater/queue.html",
            tasks=result['tasks'],
            gradings_map=gradings_map,
            include_completed=True,  # Always showing completed tasks
            pagination=result,
        )


@bp.route("/intra-rater/admin", methods=["GET"])
@roles_required("admin", "data_manager")
def intra_rater_admin() -> str:
    with get_db_session() as db:
        disease_entities = db.query(Disease).order_by(Disease.name.asc()).all()
        disease_list = [
            {"id": disease.id, "name": disease.name}
            for disease in disease_entities
        ]

        disease_ids = [d["id"] for d in disease_list]
        gradings_by_disease: dict[int, list[dict]] = {}
        if disease_ids:
            gradings = (
                db.query(DiseaseGrading)
                .filter(DiseaseGrading.disease_id.in_(disease_ids), DiseaseGrading.is_active.is_(True))
                .order_by(DiseaseGrading.disease_id.asc(), DiseaseGrading.display_order.asc())
                .all()
            )
            for grading in gradings:
                gradings_by_disease.setdefault(grading.disease_id, []).append(
                    {"id": grading.id, "impression": grading.impression}
                )

        hospitals = db.query(Hospital).order_by(Hospital.name.asc()).all()
        hospital_list = [
            {"id": hosp.id, "name": hosp.name}
            for hosp in hospitals
        ]

        lab_units = (
            db.query(LabUnit)
            .order_by(LabUnit.name.asc())
            .all()
        )
        lab_unit_list = [
            {
                "id": lu.id,
                "name": lu.name,
                "hospital_id": lu.hospital_id,
                "hospital_name": lu.hospital.name if lu.hospital else "Unknown",
            }
            for lu in lab_units
        ]

        graders = (
            db.query(User)
            .join(UserDiseaseUnitRole, UserDiseaseUnitRole.user_id == User.id)
            .filter(UserDiseaseUnitRole.active.is_(True))
            .distinct()
            .all()
        )
        grader_payload: list[dict] = []
        for user in graders:
            roles = (
                db.query(UserDiseaseUnitRole)
                .filter(UserDiseaseUnitRole.user_id == user.id, UserDiseaseUnitRole.active.is_(True))
                .all()
            )
            labs = set()
            lab_ids = set()
            diseases = set()
            disease_ids = set()
            for role in roles:
                if role.lab_unit_id:
                    lab = db.get(LabUnit, role.lab_unit_id)
                    if lab:
                        labs.add(lab.name)
                    lab_ids.add(role.lab_unit_id)
                if role.disease_id:
                    disease = db.get(Disease, role.disease_id)
                    if disease:
                        diseases.add(disease.name)
                        disease_ids.add(role.disease_id)
            grader_payload.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "lab_units": sorted(labs),
                    "lab_unit_ids": sorted(lab_ids),
                    "diseases": sorted(diseases),
                    "lab_summary": ", ".join(sorted(labs)) or "All labs",
                    "disease_summary": ", ".join(sorted(diseases)) or "All diseases",
                    "disease_ids": sorted(disease_ids),
                }
            )

        recent_batches = (
            db.query(IntraRaterBatch)
            .order_by(IntraRaterBatch.created_at.desc())
            .limit(10)
            .all()
        )
        recent_payload = []
        aggregate_counts: dict[str, dict[str, int]] = {}
        for batch in recent_batches:
            task_count = len(batch.tasks)
            graders = sorted({task.grader.full_name or task.grader.username for task in batch.tasks if task.grader})
            grader_disease_counts: dict[str, dict[str, int]] = {}
            for task in batch.tasks:
                if not task.grader or not task.disease:
                    continue
                grader_name = task.grader.full_name or task.grader.username
                disease_name = task.disease.name
                disease_map = grader_disease_counts.setdefault(grader_name, {})
                disease_map[disease_name] = disease_map.get(disease_name, 0) + 1

                agg_map = aggregate_counts.setdefault(grader_name, {})
                agg_map[disease_name] = agg_map.get(disease_name, 0) + 1
            recent_payload.append(
                {
                    "id": batch.id,
                    "disease_name": batch.disease.name if batch.disease else None,
                    "lab_unit_name": batch.lab_unit.name if batch.lab_unit else None,
                    "created_at": batch.created_at,
                    "creator_name": batch.created_by.full_name if batch.created_by else None,
                    "target_images_per_grader": batch.target_images_per_grader,
                    "image_count": task_count,
                    "graders": graders,
                    "grader_disease_counts": grader_disease_counts,
                    "cooldown": batch.cooldown_days_override,
                    "normal_grade_name": batch.normal_grade.impression if batch.normal_grade else None,
                }
            )

        default_cooldown = get_default_cooldown_days(db)

        return render_template(
            "tasks/intra_rater/admin_dashboard.html",
            diseases=disease_list,
            hospitals=hospital_list,
            lab_units=lab_unit_list,
            graders=sorted(grader_payload, key=lambda g: (g["full_name"] or g["username"])),
            recent_batches=recent_payload,
            default_cooldown=default_cooldown,
            disease_gradings=gradings_by_disease,
            aggregate_counts=aggregate_counts,
        )
