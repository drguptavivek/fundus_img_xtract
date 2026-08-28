"""REST API for project-aware discrepancy-review filter options."""
from __future__ import annotations

from flask import jsonify, request
from flask_login import current_user, login_required

from db_transaction_manager import get_db_session
from review.discrepancy_scope import (
    DiscrepancyScopeError,
    discrepancy_lab_unit_ids,
    list_discrepancy_filter_options,
)

from . import api_bp


@api_bp.route("/review/filter-options", methods=["GET"])
@login_required
def discrepancy_review_filter_options():
    project_id = request.args.get("project_id", type=int)
    with get_db_session() as db:
        try:
            options = list_discrepancy_filter_options(
                db,
                user=current_user,
                allowed_lab_unit_ids=discrepancy_lab_unit_ids(
                    db,
                    user=current_user,
                ),
                project_id=project_id,
            )
        except DiscrepancyScopeError as exc:
            return jsonify({"success": False, "error": str(exc)}), 404
    return jsonify({"success": True, "data": options.to_dict()})
