"""Routes for intra-rater task management."""

from __future__ import annotations

from http import HTTPStatus
from typing import Iterable, Sequence

from flask import Response, jsonify, request
from flask_login import current_user
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import DiseaseGrading, IntraRaterBatch, LabUnit, UserDiseaseUnitRole
from services.intra_rater_service import BatchCreateParams, IntraRaterService

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
            "items": [
                {
                    "id": batch.id,
                    "disease_id": batch.disease_id,
                    "lab_unit_id": batch.lab_unit_id,
                    "created_by_user_id": batch.created_by_user_id,
                    "cooldown_days_override": batch.cooldown_days_override,
                    "target_images_per_grader": batch.target_images_per_grader,
                    "normal_grade_id": batch.normal_grade_id,
                    "remarks": batch.remarks,
                    "created_at": batch.created_at.isoformat() if batch.created_at else None,
                    "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
                }
                for batch in batches
            ],
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
            "batch_id": batch.id,
            "selection_snapshot_json": batch.selection_snapshot_json,
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
