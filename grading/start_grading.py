from flask import redirect, url_for, flash
from flask_login import current_user
from auth.roles import roles_required
from models import Disease
from db_transaction_manager import transaction_scope
from grading.workbench_page import (
    open_linked_followup_workbench,
    open_next_workbench,
)


def register_routes(bp):
    """Register start grading routes with the blueprint."""
    bp.add_url_rule("/grade/<int:disease_id>/<string:role_slot>", view_func=start_grading, methods=["GET"])
    bp.add_url_rule(
        "/linked-followup/<int:primary_disease_id>/<int:linked_disease_id>",
        view_func=linked_followup,
        methods=["GET"],
    )


@roles_required("ophthalmologist", "field_ophthalmologist")
def start_grading(disease_id: int, role_slot: str):
    """
    Start grading for a specific disease and role slot.

    Args:
        disease_id: The ID of the disease to grade
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
    """
    # Validate role_slot
    if role_slot not in ['resident', 'resident2', 'arbitrator']:
        flash("Invalid role slot.", "danger")
        return redirect(url_for("grading.index"))

    # Check if user has the required role for the slot
    # Allow both residents and ophthalmologists to grade as residents
    if role_slot == 'resident' and not current_user.has_role('ophthalmologist', 'field_ophthalmologist'):
        flash("You don't have permission to grade as a resident.", "danger")
        return redirect(url_for("grading.index"))

    if role_slot == "resident2" and not current_user.has_role("ophthalmologist", "field_ophthalmologist"):
        flash("You don't have permission to grade in a resident slot.", "danger")
        return redirect(url_for("grading.index"))
    if role_slot == "arbitrator" and not current_user.has_role(
        "ophthalmologist", "field_ophthalmologist"
    ):
        flash("You don't have permission to grade as arbitrator.", "danger")
        return redirect(url_for("grading.index"))

    with transaction_scope() as db:
        if not db.get(Disease, disease_id):
            flash("Disease not found.", "danger")
            return redirect(url_for("grading.index"))
    # Acquisition, linked/package expansion, configuration resolution, and the
    # durable target lease are owned by the workbench service.
    return open_next_workbench(disease_id, role_slot)


@roles_required("ophthalmologist", "field_ophthalmologist")
def linked_followup(primary_disease_id: int, linked_disease_id: int):
    with transaction_scope() as db:
        primary_disease = db.get(Disease, primary_disease_id)
        linked_disease = db.get(Disease, linked_disease_id)
        if not primary_disease or not linked_disease:
            flash("Disease not found.", "danger")
            return redirect(url_for("grading.index"))
    return open_linked_followup_workbench(primary_disease_id, linked_disease_id)
