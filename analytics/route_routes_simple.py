from flask import render_template
from flask_login import current_user
from sqlalchemy import func

from auth.roles import roles_required
from .encounterUtils import get_encounters_with_non_pending_tasks
from utils.upload_eligibility import get_user_lab_unit_ids
from . import bp


@bp.route("/encounters-simple", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def encounter_results_simple():
    """Render a simplified encounter list showing only encounters with non-pending tasks."""
    
    # Get encounters with non-pending tasks using the utility function (now scoped)
    encounter_data = get_encounters_with_non_pending_tasks(current_user)
    
    return render_template(
        "analytics/results_encounters_simple.html",
        encounter_data=encounter_data
    )
