"""JSON API for durable grading workbench sessions."""

from __future__ import annotations

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.workbench.errors import WorkbenchError
from grading.workbench.service import (
    acquire_linked_followup_workbench,
    acquire_next_workbench,
    acquire_package_workbench,
    acquire_revision_workbench,
    acquire_task_workbench,
    heartbeat_workbench,
    get_submission_history,
    list_active_sessions,
    load_workbench,
    release_workbench,
    record_rejected_workbench_submission,
    resume_workbench,
    submit_workbench,
)

from . import api_bp


GRADING_ROLES = ("resident", "ophthalmologist")


@api_bp.route("/grading/workbench/me/active-sessions", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_active_workbench_sessions():
    with transaction_scope() as db:
        return jsonify({"success": True, "sessions": list_active_sessions(db, user_id=current_user.id)})


@api_bp.route("/grading/workbench/me/submissions", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_my_workbench_submissions():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return _error(WorkbenchError("limit must be an integer."))
    with transaction_scope() as db:
        return jsonify({
            "success": True,
            "submissions": get_submission_history(db, user_id=current_user.id, limit=limit),
        })


@api_bp.route("/grading/workbench/acquire", methods=["POST"])
@roles_required(*GRADING_ROLES)
def acquire_workbench_session():
    payload = request.get_json(silent=True) or {}
    try:
        disease_id = int(payload.get("disease_id"))
        lab_unit_id = int(payload["lab_unit_id"]) if payload.get("lab_unit_id") is not None else None
        with transaction_scope() as db:
            workbench, token = acquire_next_workbench(
                db,
                user_id=current_user.id,
                disease_id=disease_id,
                role_slot=str(payload.get("role_slot") or ""),
                lab_unit_id=lab_unit_id,
            )
            response = jsonify({"success": True, "workbench": workbench.to_dict(), "session_token": token})
            response.headers["Cache-Control"] = "no-store, private"
            return response, 201
    except (TypeError, ValueError):
        return _error(WorkbenchError("A valid disease_id is required."))
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/linked-followups/acquire", methods=["POST"])
@roles_required(*GRADING_ROLES)
def acquire_linked_followup_workbench_session():
    payload = request.get_json(silent=True) or {}
    try:
        primary_disease_id = int(payload.get("primary_disease_id"))
        linked_disease_id = int(payload.get("linked_disease_id"))
        with transaction_scope() as db:
            workbench, token = acquire_linked_followup_workbench(
                db,
                user_id=current_user.id,
                primary_disease_id=primary_disease_id,
                linked_disease_id=linked_disease_id,
            )
            response = jsonify({
                "success": True,
                "workbench": workbench.to_dict(),
                "session_token": token,
            })
            response.headers["Cache-Control"] = "no-store, private"
            return response, 201
    except (TypeError, ValueError):
        return _error(WorkbenchError(
            "Valid primary_disease_id and linked_disease_id values are required."
        ))
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/tasks/<string:task_uuid>/sessions", methods=["POST"])
@roles_required(*GRADING_ROLES)
def acquire_task_workbench_session(task_uuid: str):
    payload = request.get_json(silent=True) or {}
    try:
        with transaction_scope() as db:
            workbench, token = acquire_task_workbench(
                db,
                user_id=current_user.id,
                task_uuid=task_uuid,
                role_slot=str(payload.get("role_slot") or ""),
            )
            response = jsonify({"success": True, "workbench": workbench.to_dict(), "session_token": token})
            response.headers["Cache-Control"] = "no-store, private"
            return response, 201
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/grades/<int:grade_id>/revision-session", methods=["POST"])
@roles_required(*GRADING_ROLES)
def acquire_revision_workbench_session(grade_id: int):
    try:
        with transaction_scope() as db:
            workbench, token = acquire_revision_workbench(
                db, user_id=current_user.id, grade_id=grade_id
            )
            response = jsonify({"success": True, "workbench": workbench.to_dict(), "session_token": token})
            response.headers["Cache-Control"] = "no-store, private"
            return response, 201
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/packages/<string:package_uuid>/sessions", methods=["POST"])
@roles_required(*GRADING_ROLES)
def acquire_package_workbench_session(package_uuid: str):
    payload = request.get_json(silent=True) or {}
    try:
        with transaction_scope() as db:
            workbench, token = acquire_package_workbench(
                db,
                user_id=current_user.id,
                package_uuid=package_uuid,
                role_slot=str(payload.get("role_slot") or ""),
            )
            response = jsonify({"success": True, "workbench": workbench.to_dict(), "session_token": token})
            response.headers["Cache-Control"] = "no-store, private"
            return response, 201
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/sessions/<string:session_uuid>", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_workbench_session(session_uuid: str):
    try:
        with transaction_scope() as db:
            workbench = load_workbench(
                db,
                session_uuid=session_uuid,
                user_id=current_user.id,
                raw_token=_token(),
                token_generation=_generation(),
            )
            response = jsonify({"success": True, "workbench": workbench.to_dict()})
            response.headers["Cache-Control"] = "no-store, private"
            return response
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/sessions/<string:session_uuid>/resume", methods=["POST"])
@roles_required(*GRADING_ROLES)
def resume_workbench_session(session_uuid: str):
    try:
        with transaction_scope() as db:
            workbench, token = resume_workbench(db, session_uuid=session_uuid, user_id=current_user.id)
            response = jsonify({"success": True, "workbench": workbench.to_dict(), "session_token": token})
            response.headers["Cache-Control"] = "no-store, private"
            return response
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/sessions/<string:session_uuid>/heartbeat", methods=["POST"])
@roles_required(*GRADING_ROLES)
def heartbeat_workbench_session(session_uuid: str):
    try:
        with transaction_scope() as db:
            lease = heartbeat_workbench(
                db,
                session_uuid=session_uuid,
                user_id=current_user.id,
                raw_token=_token(),
                token_generation=_generation(),
            )
            return jsonify({"success": True, "lease": lease})
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/sessions/<string:session_uuid>/release", methods=["POST"])
@roles_required(*GRADING_ROLES)
def release_workbench_session(session_uuid: str):
    try:
        with transaction_scope() as db:
            release_workbench(
                db,
                session_uuid=session_uuid,
                user_id=current_user.id,
                raw_token=_token(),
                token_generation=_generation(),
            )
            return jsonify({"success": True})
    except WorkbenchError as exc:
        return _error(exc)


@api_bp.route("/grading/workbench/sessions/<string:session_uuid>/submit", methods=["POST"])
@roles_required(*GRADING_ROLES)
def submit_workbench_session(session_uuid: str):
    payload = request.get_json(silent=True) or {}
    try:
        with transaction_scope() as db:
            result = submit_workbench(
                db,
                session_uuid=session_uuid,
                user_id=current_user.id,
                raw_token=_token(),
                token_generation=_generation(),
                payload=payload,
            )
        next_payload = None
        if payload.get("action") == "save_next" and not result["idempotent_replay"]:
            queue = result.get("queue_request") or {}
            try:
                with transaction_scope() as db:
                    if queue.get("linked_followup"):
                        next_workbench, token = acquire_linked_followup_workbench(
                            db,
                            user_id=current_user.id,
                            primary_disease_id=int(queue["disease_id"]),
                            linked_disease_id=int(queue["linked_disease_id"]),
                        )
                    else:
                        next_workbench, token = acquire_next_workbench(
                            db,
                            user_id=current_user.id,
                            disease_id=int(queue["disease_id"]),
                            role_slot=str(queue["requested_slot"]),
                            lab_unit_id=queue.get("lab_unit_id"),
                        )
                    next_payload = {"workbench": next_workbench.to_dict(), "session_token": token}
            except WorkbenchError as next_error:
                next_payload = {"workbench": None, "reason": next_error.code}
        response = jsonify({
            "success": True,
            "event_uuid": result["event_uuid"],
            "idempotent_replay": result["idempotent_replay"],
            "next_workbench": next_payload,
        })
        response.headers["Cache-Control"] = "no-store, private"
        return response
    except WorkbenchError as exc:
        try:
            with transaction_scope() as audit_db:
                record_rejected_workbench_submission(
                    audit_db,
                    user_id=current_user.id,
                    session_uuid=session_uuid,
                    result_code=exc.code,
                    action=str(payload.get("action") or "submit"),
                )
        except Exception:
            # Audit failure must not hide the safe domain error response.
            pass
        return _error(exc)


def _token() -> str:
    return (request.headers.get("X-Workbench-Token") or "").strip()


def _generation() -> int:
    try:
        return int(request.headers.get("X-Workbench-Generation") or 0)
    except ValueError:
        return 0


def _error(exc: WorkbenchError):
    return jsonify({"success": False, "error": exc.to_dict()}), exc.status_code
