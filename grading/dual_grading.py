"""Compatibility transports for the consolidated grading workbench.

Ordinary grading business rules and writes live in ``grading.workbench``.
These endpoint names remain so existing bookmarks and cached forms continue
to work during rollout.
"""

from __future__ import annotations

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.workbench.errors import WorkbenchError
from grading.workbench.legacy_transport import submit_task_form
from grading.workbench_page import open_revision_workbench, open_task_workbench
from models import Grade, GradingTask, ImageMetadata
from utils.dualGradingEligibility import get_user_eligibility_for_task


def register_routes(bp):
    bp.add_url_rule(
        "/task/<string:task_uuid>/<string:slot_type>",
        view_func=dual_grading_task,
        methods=["GET"],
    )
    bp.add_url_rule("/task/submit", view_func=dual_grading_submit, methods=["POST"])
    bp.add_url_rule("/revise/<int:grade_id>", view_func=revise_grading, methods=["GET"])
    bp.add_url_rule(
        "/task/<string:task_uuid>/feature-geometry",
        view_func=dual_grading_feature_geometry,
        methods=["GET"],
    )


@roles_required("resident", "ophthalmologist", "admin")
def revise_grading(grade_id: int):
    return open_revision_workbench(grade_id)


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_task(task_uuid: str, slot_type: str):
    return open_task_workbench(task_uuid, slot_type)


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_submit():
    try:
        with transaction_scope() as db:
            result = submit_task_form(db, user_id=current_user.id, form=request.form)
        flash("Grade submitted successfully.", "success")
        if (request.form.get("action") or "").strip().lower() == "save_next":
            queue = result.get("queue_request") or {}
            return redirect(url_for(
                "grading.start_grading",
                disease_id=queue.get("disease_id"),
                role_slot=queue.get("requested_slot"),
            ))
    except WorkbenchError as exc:
        flash(str(exc), "warning")
    return redirect(url_for("grading.index"))


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_feature_geometry(task_uuid: str):
    slot = (request.args.get("slot") or "").strip()
    if slot not in {"resident", "resident2", "arbitrator"}:
        return jsonify({"success": False, "message": "Invalid grading slot."}), 422
    with transaction_scope() as db:
        task = db.query(GradingTask).filter(GradingTask.uuid == task_uuid).first()
        if task is None:
            return jsonify({"success": False, "message": "Task not found."}), 404
        grade = (
            db.query(Grade)
            .filter(
                Grade.task_id == task.id,
                Grade.grader_user_id == current_user.id,
                Grade.role_slot == slot,
            )
            .first()
        )
        if grade is None and not get_user_eligibility_for_task(
            db, current_user.id, task.id, slot
        ):
            return jsonify({"success": False, "message": "Not eligible to view geometry."}), 403
        image_uuid = _resolve_task_image_uuid(task)
        metadata = _fetch_image_metadata(db, image_uuid)
        return jsonify({
            "success": True,
            "task_uuid": task.uuid,
            "slot": slot,
            "feature_geometry": grade.feature_geometry_json if grade else None,
            "image": {
                "uuid": image_uuid,
                "width": metadata.width if metadata else None,
                "height": metadata.height if metadata else None,
            },
        })


def _fetch_image_metadata(db, image_uuid: str | None) -> ImageMetadata | None:
    if not image_uuid:
        return None
    return (
        db.query(ImageMetadata)
        .filter(
            ImageMetadata.image_uuid == image_uuid,
            ImageMetadata.image_variant == "orig",
        )
        .first()
    )


def _resolve_task_image_uuid(task: GradingTask) -> str | None:
    if task.encounter_file:
        return task.encounter_file.uuid
    if task.direct_image:
        return task.direct_image.uuid
    if task.encounter_set_image:
        return task.encounter_set_image.uuid
    return None


def _missing_task_image_reference(task: GradingTask) -> str | None:
    if task.encounter_file_id:
        return f"Encounter file ID {task.encounter_file_id}"
    if task.direct_image_upload_id:
        return f"Direct upload ID {task.direct_image_upload_id}"
    if task.encounter_set_image_id:
        return f"EncounterSet image ID {task.encounter_set_image_id}"
    if task.patient_encounter_id:
        return f"Patient encounter ID {task.patient_encounter_id}"
    return None
