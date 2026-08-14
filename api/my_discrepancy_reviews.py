"""REST API for reviewer-owned discrepancy-review history."""
from __future__ import annotations

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_or_project_grant_required
from db_transaction_manager import get_db_session
from review.my_discrepancy_reviews import my_discrepancy_review_page

from . import api_bp


@api_bp.route("/review/me/discrepancy-reviews", methods=["GET"])
@roles_or_project_grant_required("discrepancy_reviewer")
def get_my_discrepancy_reviews():
    """Return the signed-in reviewer's scoped discrepancy-review history."""
    page = max(1, request.args.get("page", 1, type=int) or 1)
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int) or 20))
    disease_id = request.args.get("disease_id", type=int)
    try:
        with get_db_session() as db:
            history = my_discrepancy_review_page(
                db,
                user=current_user._get_current_object(),
                requested_date_from=request.args.get("date_from"),
                requested_date_to=request.args.get("date_to"),
                disease_id=disease_id,
                page=page,
                per_page=per_page,
            )
            return jsonify({"success": True, "data": history.to_dict()})
    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": {"code": "invalid_review_filter", "message": str(exc)},
        }), 400
