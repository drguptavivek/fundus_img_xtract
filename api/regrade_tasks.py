"""JSON and HTMX API for regrade queue creation and adjudication submission."""

from __future__ import annotations

import json

from flask import flash, jsonify, make_response, request, url_for
from flask_login import current_user

from auth.decorators import session_or_token_auth_required
from db_transaction_manager import transaction_scope
from models import User
from regrade import (
    CreateRegradeTasksInput,
    RegradeError,
    SubmitRegradeInput,
    create_regrade_tasks,
    submit_regrade,
)

from . import api_bp


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _payload() -> dict[str, object]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    if request.form:
        list_fields = {
            "resident_grade",
            "resident2_grade",
            "arbitrator_grade",
            "review_grade",
            "final_grade",
            "regrade_grade",
            "ai_model_id",
            "ai_grade",
            "ai_review_status",
            "task_ids",
            "selected_features",
        }
        return {
            key: request.form.getlist(key) if key in list_fields else request.form.get(key)
            for key in request.form
        }
    raise RegradeError(
        "A JSON object or form body is required.",
        code="invalid_request_body",
        status_code=400,
    )


def _actor(db) -> User:
    if current_user.is_authenticated:
        actor_id = current_user.id
    else:
        actor_id = (getattr(request, "mobile_auth", {}) or {}).get("user_id")
    if not actor_id:
        raise RegradeError("Authentication is required.", code="unauthorized", status_code=401)
    actor = db.query(User).filter(User.id == int(actor_id), User.is_active.is_(True)).first()
    if actor is None:
        raise RegradeError("Authentication is invalid.", code="unauthorized", status_code=401)
    return actor


def _success(payload: dict[str, object], *, status: int, redirect_url: str):
    if not _is_htmx():
        return jsonify({"success": True, **payload}), status
    flash(str(payload.get("message") or "Regrade operation completed."), "success")
    response = make_response("", 204)
    response.headers["HX-Redirect"] = redirect_url
    return response


def _error(exc: RegradeError):
    body = {
        "success": False,
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    }
    response = jsonify(body)
    response.status_code = exc.status_code
    if _is_htmx():
        response.headers["HX-Trigger"] = json.dumps(
            {"regrade:error": {"message": exc.message}}
        )
    return response


@api_bp.route("/regrade-tasks", methods=["POST"])
@session_or_token_auth_required
def create_regrade_tasks_api():
    """Create a fail-closed regrade cohort from discrepancy filters."""
    try:
        command = CreateRegradeTasksInput.from_payload(_payload())
        with transaction_scope() as db:
            result = create_regrade_tasks(db, actor=_actor(db), command=command)
        message = (
            f"Regrade tasks created: {result['created_count']}. "
            f"Skipped existing pending: {result['skipped_pending_count']}."
        )
        return _success(
            {"result": result, "message": message},
            status=201,
            redirect_url=request.referrer
            or url_for("review.regrade_task_creator", disease_id=command.disease_id),
        )
    except RegradeError as exc:
        return _error(exc)


@api_bp.route("/regrade-tasks/<int:regrade_task_id>/submission", methods=["POST"])
@session_or_token_auth_required
def submit_regrade_api(regrade_task_id: int):
    """Submit or revise the assigned regrade and update consensus in place."""
    try:
        payload = _payload()
        command = SubmitRegradeInput.from_payload(payload)
        with transaction_scope() as db:
            result = submit_regrade(
                db,
                actor=_actor(db),
                regrade_task_id=regrade_task_id,
                command=command,
            )
        save_next = payload.get("action") == "save_next"
        result["next_url"] = (
            url_for("grading.start_random_regrade_task")
            if save_next
            else url_for("grading.regrade_tasks")
        )
        return _success(
            {"submission": result, "message": "Regrade submitted successfully."},
            status=200,
            redirect_url=str(result["next_url"]),
        )
    except RegradeError as exc:
        return _error(exc)
