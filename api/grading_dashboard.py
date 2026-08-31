"""Grader-facing eligibility and mixed history APIs."""
from __future__ import annotations

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.dashboard_service import grader_eligibility_dto, grading_history_page
from grading.queue_cards import disease_queue_card, grader_queue_overview

from . import api_bp


GRADING_ROLES = ("ophthalmologist", "field_ophthalmologist")


@api_bp.route("/grading/me/eligibility", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_my_grading_eligibility():
    with transaction_scope() as db:
        return jsonify({
            "success": True,
            "eligibility": grader_eligibility_dto(db, user_id=current_user.id),
        })


@api_bp.route("/grading/me/queues", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_my_grading_queues():
    """Both grading queue panels for the current grader.

    Returns ``project_encounter_sets`` with their counts, and
    ``legacy_diseases`` without counts - the latter are fetched per disease
    from ``/grading/me/queues/<disease_id>`` so the dashboard can paint before
    any queue has been counted.
    """
    with transaction_scope() as db:
        return jsonify({
            "success": True,
            **grader_queue_overview(db, user_id=current_user.id),
        })


@api_bp.route("/grading/me/queues/<int:disease_id>", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_my_grading_queue(disease_id: int):
    """Pending totals and linked follow-ups for one disease queue."""
    with transaction_scope() as db:
        card = disease_queue_card(db, user_id=current_user.id, disease_id=disease_id)
        if card is None:
            return jsonify({
                "success": False,
                "error": {
                    "code": "disease_not_gradable",
                    "message": "No active grading eligibility for this disease.",
                },
            }), 404
        return jsonify({"success": True, "queue": card})


@api_bp.route("/grading/me/history", methods=["GET"])
@roles_required(*GRADING_ROLES)
def get_my_grading_history():
    try:
        page = max(1, request.args.get("page", default=1, type=int) or 1)
        per_page = min(
            50,
            max(1, request.args.get("per_page", default=12, type=int) or 12),
        )
        disease_id = request.args.get("disease_id", default=None, type=int)
        with transaction_scope() as db:
            history = grading_history_page(
                db,
                user_id=current_user.id,
                requested_date=request.args.get("date"),
                history_type=request.args.get("type", "all"),
                disease_id=disease_id,
                page=page,
                per_page=per_page,
            )
            return jsonify({"success": True, "history": history.to_dict()})
    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": {"code": "invalid_history_filter", "message": str(exc)},
        }), 400
