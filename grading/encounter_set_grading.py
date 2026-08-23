"""
Encounter Set Grading Routes

Implements the grading interface for encounter-set based diseases (e.g., Strabismus).
Features:
- Sync-grid viewer for all images in the set
- Consolidated grading submission for the entire set
- Not-gradable handling for incomplete sets
"""

from flask import render_template, redirect, url_for, request, jsonify, abort, flash
from flask_login import login_required, current_user
from auth.roles import roles_required
from grading_schemes.service import STANDARD_NON_GRADABLE_REASONS
from models import PatientEncounters, EncounterSetImage, GradingTask, Disease, DiseaseGrading, Grade
from db_transaction_manager import transaction_scope
from utils.log_sanitize import sanitize_log_value
from sqlalchemy import select, and_
import logging

logger = logging.getLogger("grading.encounter_set")


def register_routes(bp):
    """Register encounter-set grading routes with the blueprint."""
    from flask import Blueprint

    bp.add_url_rule("/encounter_set/<uuid>", view_func=encounter_set_grading, methods=["GET"])
    bp.add_url_rule("/encounter_set/submit", view_func=encounter_set_submit, methods=["POST"])


@login_required
@roles_required("resident2", "ophthalmologist", "arbitrator", "admin")
def encounter_set_grading(uuid):
    """Display encounter set for grading with sync-grid viewer."""
    with transaction_scope() as db:
        task = db.query(GradingTask).filter_by(uuid=uuid).first()
        if not task:
            flash("Grading task not found.", "danger")
            return redirect(url_for("grading.index"))

        if not task.patient_encounter_id:
            flash("This is not an encounter-set grading task.", "warning")
            return redirect(url_for("grading.index"))

        encounter = db.query(PatientEncounters).filter_by(id=task.patient_encounter_id).first()
        if not encounter:
            flash("Encounter not found.", "danger")
            return redirect(url_for("grading.index"))

        # Get all images in the set, ordered by spatial position
        images = db.query(EncounterSetImage).filter_by(
            patient_encounter_id=encounter.id
        ).order_by(EncounterSetImage.spatial_position).all()

        # Create a 1-9 mapping (5 for Strabismus, but UI can handle empty slots)
        grid = {i: None for i in range(1, 10)}
        for img in images:
            if 1 <= img.spatial_position <= 9:
                grid[img.spatial_position] = img

        # Get disease grading labels
        disease = db.query(Disease).filter_by(id=task.disease_id).first()
        grading_labels = db.query(DiseaseGrading).filter_by(
            disease_id=task.disease_id,
            is_active=True
        ).order_by(DiseaseGrading.display_order).all()

        # Check if user has already graded this task
        existing_grade = db.query(Grade).filter_by(
            task_id=task.id,
            grader_user_id=current_user.id
        ).first()

        # Count not-gradable images
        not_gradable_count = sum(1 for img in images if img.is_not_gradable)

        return render_template(
            "grading/encounter_set_grading.html",
            task=task,
            encounter=encounter,
            grid=grid,
            images=images,
            disease=disease,
            grading_labels=grading_labels,
            existing_grade=existing_grade,
            not_gradable_count=not_gradable_count,
            non_gradable_reasons=list(STANDARD_NON_GRADABLE_REASONS),
        )


@login_required
@roles_required("resident2", "ophthalmologist", "arbitrator", "admin")
def encounter_set_submit():
    """Submit grade for an encounter set."""
    from auth.utils import utcnow

    data = request.form
    task_uuid = data.get("task_uuid")
    slot = data.get("slot")  # resident, resident2, arbitrator

    if not task_uuid or not slot:
        return jsonify({"success": False, "message": "Missing task_uuid or slot"}), 400

    with transaction_scope() as db:
        task = db.query(GradingTask).filter_by(uuid=task_uuid).first()
        if not task:
            return jsonify({"success": False, "message": "Task not found"}), 404

        # Validate slot and use it as-is for role_slot (string field)
        valid_slots = {"resident", "resident2", "arbitrator"}
        if slot not in valid_slots:
            return jsonify({"success": False, "message": f"Invalid slot: {slot}"}), 400
        role_slot = slot

        label_id = data.get("label_id", type=int)
        if not label_id:
            return jsonify({"success": False, "message": "Missing label_id"}), 400

        # Check if user is revising an existing grade
        existing_grade = db.query(Grade).filter_by(
            task_id=task.id,
            grader_user_id=current_user.id
        ).first()

        if existing_grade:
            # Update existing grade
            existing_grade.disease_grading_id = label_id
            existing_grade.comment = data.get("comment", "")
            existing_grade.updated_at = utcnow()

            logger.info("Grade revised for task %s by user %s",
                       sanitize_log_value(task_uuid), current_user.username)
        else:
            # Create new grade
            grade = Grade(
                task_id=task.id,
                grader_user_id=current_user.id,
                role_slot=role_slot,
                disease_grading_id=label_id,
                comment=data.get("comment", ""),
                created_at=utcnow()
            )
            db.add(grade)

            logger.info("Grade submitted for task %s by user %s",
                       sanitize_log_value(task_uuid), current_user.username)

        # Update task state and create consensus (using existing services)
        from utils.dualGradingConsensusUtils import update_task_state_based_on_grades, create_or_update_consensus
        update_task_state_based_on_grades(task.id, db)
        create_or_update_consensus(task.id, db)

        flash("Grade submitted successfully.", "success")
        return redirect(url_for("grading.index"))
