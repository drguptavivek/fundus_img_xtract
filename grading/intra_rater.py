"""
Inline intra-rater grading routes surfaced within the dual grading flow.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from flask import (
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)
from flask_login import current_user
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import IntraRaterTask
from services.intra_rater_service import IntraRaterService, SubmitGradeParams, STATE_PENDING
from utils.dualGradingGetNextTasks import (
    get_next_eligible_arbitrator_task_atomic,
    get_next_eligible_resident2_task_atomic,
    get_next_eligible_resident_task_atomic,
)
from utils.masterUtils import fetch_active_disease_gradings


def _build_intra_task_url(task_uuid: str, resume_slot: Optional[str], resume_disease_id: Optional[int]) -> str:
    """Construct intra-rater task URL while preserving flow metadata."""
    params = {"task_uuid": task_uuid}
    if resume_slot:
        params["resume_slot"] = resume_slot
    if resume_disease_id:
        params["resume_disease_id"] = resume_disease_id
    return url_for("grading.intra_rater_task", **params)


def register_routes(bp) -> None:
    """Register intra-rater grading routes."""
    bp.add_url_rule("/intra-task/<string:task_uuid>", view_func=intra_rater_task, methods=["GET"])
    bp.add_url_rule("/intra-task/submit", view_func=intra_rater_submit, methods=["POST"])


@roles_required("resident", "ophthalmologist", "admin")
def intra_rater_task(task_uuid: str):
    """Display a pending intra-rater reassessment."""
    resume_slot = (request.args.get("resume_slot") or "").strip().lower() or None
    resume_disease_id = request.args.get("resume_disease_id", type=int)

    if resume_slot not in {"resident", "resident2", "arbitrator"}:
        resume_slot = None
    task_uuid = (task_uuid or "").strip()
    if not task_uuid:
        flash("Invalid intra-rater task reference.", "danger")
        return redirect(url_for("grading.index"))

    with transaction_scope() as db:
        task: Optional[IntraRaterTask] = (
            db.query(IntraRaterTask)
            .options(
                selectinload(IntraRaterTask.disease),
                selectinload(IntraRaterTask.lab_unit),
                selectinload(IntraRaterTask.encounter_file),
                selectinload(IntraRaterTask.direct_image_upload),
            )
            .filter(IntraRaterTask.uuid == task_uuid)
            .first()
        )

        if task is None:
            flash("Intra-rater task not found.", "danger")
            return redirect(url_for("grading.index"))

        if task.grader_user_id != current_user.id:
            flash("You are not authorized to view this intra-rater task.", "danger")
            return redirect(url_for("grading.index"))

        if task.state != STATE_PENDING:
            flash("This intra-rater task is no longer available.", "info")
            return redirect(url_for("grading.index"))

        if not task.uuid:
            from uuid import uuid4

            task.uuid = str(uuid4())
            db.add(task)
            db.flush()
            task_uuid = task.uuid

        disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
        if not disease_gradings:
            flash("No disease gradings available for this intra-rater task.", "danger")
            return redirect(url_for("grading.index"))

        grading_guidelines = {grading.id: grading.guidelines for grading in disease_gradings}

        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image_upload:
            image_uuid = task.direct_image_upload.uuid

        start_time_iso = datetime.now(timezone.utc).isoformat()
        start_time_key = f"intra_grading_start_time_{task_uuid}"
        flask_session[start_time_key] = start_time_iso

        effective_resume_disease_id = resume_disease_id or task.disease_id

        return render_template(
            "grading/intra_grading_task.html",
            task=task,
            disease_gradings=disease_gradings,
            grading_guidelines=grading_guidelines,
            image_uuid=image_uuid,
            resume_slot=resume_slot,
            resume_disease_id=effective_resume_disease_id,
            start_time_iso=start_time_iso,
            current_user_id=getattr(current_user, "id", None),
        )


@roles_required("resident", "ophthalmologist", "admin")
def intra_rater_submit():
    """Persist an intra-rater grade and continue the grading flow."""
    action = (request.form.get("action") or "").strip().lower()
    task_uuid = (request.form.get("task_uuid") or "").strip()
    label_id = request.form.get("label_id", type=int)
    comment = (request.form.get("comment") or "").strip() or None
    resume_slot = (request.form.get("resume_slot") or "").strip().lower() or None
    resume_disease_id = request.form.get("resume_disease_id", type=int)
    start_time_iso = (request.form.get("start_time_iso") or "").strip() or None
    actual_resume_disease_id = resume_disease_id
    if resume_slot not in {"resident", "resident2", "arbitrator"}:
        resume_slot = None

    if not task_uuid:
        flash("Invalid intra-rater task identifier.", "danger")
        return redirect(url_for("grading.index"))

    if not label_id or not isinstance(label_id, int) or label_id <= 0:
        flash("Select a valid grading option before submitting.", "danger")
        return redirect(_build_intra_task_url(task_uuid, resume_slot, resume_disease_id))

    with transaction_scope() as db:
        task: Optional[IntraRaterTask] = (
            db.query(IntraRaterTask)
            .options(selectinload(IntraRaterTask.disease))
            .filter(IntraRaterTask.uuid == task_uuid)
            .with_for_update()
            .first()
        )

        if task is None:
            flash("Intra-rater task not found or already removed.", "danger")
            return redirect(url_for("grading.index"))

        if task.grader_user_id != current_user.id:
            flash("You are not authorized to submit this intra-rater task.", "danger")
            return redirect(url_for("grading.index"))

        if task.state != STATE_PENDING:
            flash("This intra-rater task has already been completed.", "info")
            return redirect(url_for("grading.index"))

        if not task.uuid:
            from uuid import uuid4

            task.uuid = str(uuid4())
            db.add(task)
            db.flush()
            task_uuid = task.uuid

        time_taken = None
        start_time = None
        if start_time_iso:
            try:
                parsed_start = datetime.fromisoformat(start_time_iso)
                if parsed_start.tzinfo is None:
                    parsed_start = parsed_start.replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                time_taken = int((current_time - parsed_start).total_seconds())
                start_time = parsed_start
            except ValueError:
                start_time = None
                time_taken = None

        start_time_key = f"intra_grading_start_time_{task_uuid}"
        stored_start_iso = flask_session.pop(start_time_key, None)
        if stored_start_iso and time_taken is None:
            try:
                parsed_start = datetime.fromisoformat(stored_start_iso)
                if parsed_start.tzinfo is None:
                    parsed_start = parsed_start.replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                time_taken = int((current_time - parsed_start).total_seconds())
                start_time = parsed_start
            except (TypeError, ValueError):  # pragma: no cover - defensive
                start_time = None
                time_taken = None

        actual_resume_disease_id = resume_disease_id or task.disease_id

        service = IntraRaterService(db)
        params = SubmitGradeParams(
            task_id=task.id,
            grader_user_id=current_user.id,
            disease_grading_id=label_id,
            comment=comment,
            time_taken=time_taken,
            start_time=start_time,
        )

        try:
            service.submit_grade(params)
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(_build_intra_task_url(task_uuid, resume_slot, actual_resume_disease_id))

    flash("Grade submitted successfully.", "success")

    if action == "save_next" and resume_slot in {"resident", "resident2", "arbitrator"} and actual_resume_disease_id:
        next_task = None
        try:
            if resume_slot == "resident":
                next_task = get_next_eligible_resident_task_atomic(current_user.id, actual_resume_disease_id)
            elif resume_slot == "resident2":
                next_task = get_next_eligible_resident2_task_atomic(current_user.id, actual_resume_disease_id)
            elif resume_slot == "arbitrator":
                next_task = get_next_eligible_arbitrator_task_atomic(current_user.id, actual_resume_disease_id)
        except Exception as exc:  # pragma: no cover - defensive logging via flash
            flash("Next task could not be loaded after intra-rater submission.", "warning")
            return redirect(url_for("grading.index"))

        if next_task is None:
            flash("No more tasks available in the current grading queue.", "info")
            return redirect(url_for("grading.index"))

        if isinstance(next_task, str):
            flash(next_task, "info")
            return redirect(url_for("grading.index"))

        return redirect(url_for("grading.dual_grading_task", task_uuid=next_task.uuid, slot_type=resume_slot))

    return redirect(url_for("grading.index"))
