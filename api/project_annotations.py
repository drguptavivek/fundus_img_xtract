"""Project annotation policy administration and schema export API."""

import json

from flask import Response, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import GradingTask
from project_annotations.errors import (
    AnnotationPolicyAccessDenied,
    AnnotationPolicyConflictError,
    AnnotationPolicyNotFound,
    AnnotationPolicyValidationError,
)
from project_annotations.service import (
    get_project_policy_configuration,
    parse_policy_update,
    save_project_policy,
    resolve_task_annotation_context,
)
from utils.dualGradingEligibility import get_user_eligibility_for_task
from project_annotations.schema_export import (
    build_project_schema_export,
    project_schema_filename,
    serialize_project_schema_toml,
)

from . import api_bp


@api_bp.route("/grading-tasks/<string:task_uuid>/annotation-context", methods=["GET"])
@login_required
def get_task_annotation_context(task_uuid: str):
    """Return the server-resolved project policy for one accessible task."""
    slot = (request.args.get("slot") or "").strip()
    if slot not in {"resident", "resident2", "arbitrator"}:
        return jsonify({"error": "validation_error", "message": "A valid grading slot is required."}), 422
    with transaction_scope() as db:
        task = (
            db.query(GradingTask)
            .options(
                selectinload(GradingTask.encounter_file),
                selectinload(GradingTask.direct_image),
                selectinload(GradingTask.patient_encounter),
                selectinload(GradingTask.encounter_set_image),
            )
            .filter(GradingTask.uuid == task_uuid)
            .first()
        )
        if task is None:
            return jsonify({"error": "not_found", "message": "Grading task not found."}), 404
        if not get_user_eligibility_for_task(
            db, current_user.id, task.id, slot
        ):
            return jsonify({"error": "access_denied", "message": "Task is outside your grading scope."}), 403
        response = jsonify(resolve_task_annotation_context(db, task).to_dict())
        response.headers["Cache-Control"] = "no-store, private"
        return response


@api_bp.route("/projects/<int:project_id>/annotation-policy", methods=["GET"])
@roles_required("admin")
def get_project_annotation_policy(project_id: int):
    try:
        with transaction_scope() as db:
            context = get_project_policy_configuration(
                db,
                project_id,
                actor_user_id=current_user.id,
            )
            return jsonify(context.to_dict())
    except AnnotationPolicyNotFound as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except AnnotationPolicyAccessDenied as exc:
        return jsonify({"error": "access_denied", "message": str(exc)}), 403


@api_bp.route("/projects/<int:project_id>/annotation-policy", methods=["PUT"])
@roles_required("admin")
def put_project_annotation_policy(project_id: int):
    try:
        update = parse_policy_update(request.get_json(silent=True))
        with transaction_scope() as db:
            context = save_project_policy(
                db,
                project_id=project_id,
                actor_user_id=current_user.id,
                update=update,
            )
            return jsonify(context.to_dict())
    except AnnotationPolicyNotFound as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except AnnotationPolicyAccessDenied as exc:
        return jsonify({"error": "access_denied", "message": str(exc)}), 403
    except AnnotationPolicyConflictError as exc:
        return jsonify({"error": "stale_revision", "message": str(exc)}), 409
    except AnnotationPolicyValidationError as exc:
        return jsonify({"error": "validation_error", "message": str(exc)}), 422


@api_bp.route("/projects/<int:project_id>/schema.<string:export_format>", methods=["GET"])
@roles_required("admin")
def export_project_schema(project_id: int, export_format: str):
    """Download the project annotation and classification schema."""
    if export_format not in {"json", "toml"}:
        return jsonify({"error": "not_found", "message": "Unsupported schema export format."}), 404
    try:
        with transaction_scope() as db:
            schema = build_project_schema_export(
                db,
                project_id=project_id,
                actor_user_id=current_user.id,
            )
    except AnnotationPolicyNotFound as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except AnnotationPolicyAccessDenied as exc:
        return jsonify({"error": "access_denied", "message": str(exc)}), 403

    filename = project_schema_filename(schema["project"]["code"], export_format)
    if export_format == "toml":
        content = serialize_project_schema_toml(schema)
        mimetype = "application/toml"
    else:
        content = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        mimetype = "application/json"
    response = Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    response.headers["Cache-Control"] = "no-store"
    return response
