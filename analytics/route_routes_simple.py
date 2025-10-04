from flask import render_template
from flask_login import current_user
from sqlalchemy import func

from auth.roles import roles_required
from models import Session
from .encounterUtils import get_encounters_with_non_pending_tasks
from utils.upload_eligibility import get_user_lab_unit_ids
from . import bp


@bp.route("/encounters-simple", methods=["GET"])
@roles_required("admin", "data_manager")
def encounter_results_simple():
    """Render a simplified encounter list showing only encounters with non-pending tasks."""
    
    # Get user's lab unit access
    user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    is_admin_like = current_user.has_role("admin", "data_manager")
    
    # Get encounters with non-pending tasks using the utility function, passing user permissions
    encounter_data = get_encounters_with_non_pending_tasks(user_lab_unit_ids, is_admin_like)
    
    return render_template(
        "analytics/results_encounters_simple.html",
        encounter_data=encounter_data
    )