from __future__ import annotations

from flask_login import login_required

from . import bp
from .route_discrepancy_review import (
    render_discrepancy_review,
)


@bp.route("/regrade-task-creator", methods=["GET"])
@login_required
def regrade_task_creator():
    enforced_filters = {
        "resident_compare": "mismatch",
        "has_arbitrator": "yes",
        "has_regrade": "no",
    }
    return render_discrepancy_review(
        page_title="Regrade Task Creator",
        enforced_filters=enforced_filters,
    )
