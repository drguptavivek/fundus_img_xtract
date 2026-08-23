from flask import redirect, url_for, flash
from flask_login import current_user
from auth.roles import roles_required
from models import Disease
from db_transaction_manager import transaction_scope
from grading.workbench.errors import ActiveSessionExists, WorkbenchError
from grading.workbench.service import (
    acquire_linked_followup_workbench,
    acquire_next_workbench,
    resume_workbench,
)
from grading.workbench_page import remember_session_token
  

def register_routes(bp):
    """Register start grading routes with the blueprint."""
    bp.add_url_rule("/grade/<int:disease_id>/<string:role_slot>", view_func=start_grading, methods=["GET"])
    bp.add_url_rule(
        "/linked-followup/<int:primary_disease_id>/<int:linked_disease_id>",
        view_func=linked_followup,
        methods=["GET"],
    )


@roles_required("ophthalmologist")
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
    if role_slot == 'resident' and not (current_user.has_role('resident') or current_user.has_role('ophthalmologist')):
        flash("You don't have permission to grade as a resident.", "danger")
        return redirect(url_for("grading.index"))
    
    if role_slot == "resident2" and not current_user.has_role("resident", "ophthalmologist"):
        flash("You don't have permission to grade in a resident slot.", "danger")
        return redirect(url_for("grading.index"))
    if role_slot == "arbitrator" and not current_user.has_role("ophthalmologist"):
        flash("You don't have permission to grade as arbitrator.", "danger")
        return redirect(url_for("grading.index"))
    
    # Acquisition, linked/package expansion, configuration resolution, and the
    # durable target lease are owned by the workbench service.
    with transaction_scope() as db:
        disease = db.get(Disease, disease_id)
        if not disease:
            flash("Disease not found.", "danger")
            return redirect(url_for("grading.index"))
        try:
            workbench, token = acquire_next_workbench(
                db,
                user_id=current_user.id,
                disease_id=disease_id,
                role_slot=role_slot,
            )
        except ActiveSessionExists as exc:
            active_uuid = str(exc.details.get("session_uuid") or "")
            if not active_uuid:
                flash(str(exc), "warning")
                return redirect(url_for("grading.index"))
            workbench, token = resume_workbench(
                db, session_uuid=active_uuid, user_id=current_user.id
            )
        except WorkbenchError as exc:
            flash(str(exc), "info")
            return redirect(url_for("grading.index"))
        remember_session_token(
            workbench.lease.session_uuid,
            token,
            workbench.lease.token_generation,
        )
        return redirect(
            url_for("grading.workbench_page", session_uuid=workbench.lease.session_uuid)
        )


@roles_required("ophthalmologist")
def linked_followup(primary_disease_id: int, linked_disease_id: int):
    with transaction_scope() as db:
        primary_disease = db.query(Disease).filter(Disease.id == primary_disease_id).first()
        linked_disease = db.query(Disease).filter(Disease.id == linked_disease_id).first()
        if not primary_disease or not linked_disease:
            flash("Disease not found.", "danger")
            return redirect(url_for("grading.index"))

        try:
            workbench, token = acquire_linked_followup_workbench(
                db,
                user_id=current_user.id,
                primary_disease_id=primary_disease_id,
                linked_disease_id=linked_disease_id,
            )
        except ActiveSessionExists as exc:
            active_uuid = str(exc.details.get("session_uuid") or "")
            if not active_uuid:
                flash(str(exc), "warning")
                return redirect(url_for("grading.index"))
            workbench, token = resume_workbench(
                db, session_uuid=active_uuid, user_id=current_user.id
            )
        except WorkbenchError as exc:
            flash(str(exc), "info")
            return redirect(url_for("grading.index"))
        remember_session_token(
            workbench.lease.session_uuid,
            token,
            workbench.lease.token_generation,
        )
        return redirect(url_for(
            "grading.workbench_page", session_uuid=workbench.lease.session_uuid
        ))
