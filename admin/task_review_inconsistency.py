from __future__ import annotations

from datetime import datetime, timezone
import sqlalchemy as sa
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import (
    Consensus,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    LabUnit,
    User,
)


def _latest_review_subquery():
    """Return subquery with latest review grade per task."""
    return (
        sa.select(
            Grade.task_id.label("task_id"),
            Grade.id.label("review_grade_id"),
            Grade.disease_grading_id.label("review_grading_id"),
            Grade.grade_name.label("review_impression"),
            Grade.updated_at.label("review_updated_at"),
            Grade.grader_user_id.label("reviewer_user_id"),
            sa.func.row_number()
            .over(
                partition_by=Grade.task_id,
                order_by=[Grade.updated_at.desc().nullslast(), Grade.id.desc()],
            )
            .label("rn"),
        )
        .where(Grade.role_slot == "review")
        .subquery()
    )


@roles_required("admin", "data_manager")
@login_required
def task_review_inconsistency():
    """List tasks where review grade differs from consensus or consensus is missing."""
    disease_id = request.args.get("disease_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    state = request.args.get("state") or None

    with transaction_scope() as db:
        diseases = [
            {"id": d.id, "name": d.name}
            for d in db.query(Disease).order_by(Disease.name).all()
        ]
        lab_units = [
            {"id": lu.id, "name": lu.name, "hospital_name": (lu.hospital.name if lu.hospital else "")}
            for lu in db.query(LabUnit).join(LabUnit.hospital).order_by(LabUnit.hospital_id, LabUnit.name).all()
        ]

        latest_review = _latest_review_subquery()

        base = (
            db.query(
                GradingTask.id.label("task_id"),
                GradingTask.state,
                Disease.name.label("disease_name"),
                LabUnit.name.label("lab_unit_name"),
                Consensus.final_disease_grading_id,
                Consensus.method.label("consensus_method"),
                DiseaseGrading.impression.label("consensus_impression"),
                DiseaseGrading.id.label("consensus_grading_id"),
                latest_review.c.review_grading_id,
                latest_review.c.review_impression,
                latest_review.c.review_updated_at,
                latest_review.c.reviewer_user_id,
                User.username.label("reviewer_username"),
            )
            .join(latest_review, latest_review.c.task_id == GradingTask.id)
            .outerjoin(Consensus, Consensus.task_id == GradingTask.id)
            .outerjoin(DiseaseGrading, DiseaseGrading.id == Consensus.final_disease_grading_id)
            .outerjoin(Disease, Disease.id == GradingTask.disease_id)
            .outerjoin(LabUnit, LabUnit.id == GradingTask.lab_unit_id)
            .outerjoin(User, User.id == latest_review.c.reviewer_user_id)
            .filter(latest_review.c.rn == 1)
            .filter(
                sa.or_(
                    Consensus.final_disease_grading_id.is_(None),
                    Consensus.final_disease_grading_id != latest_review.c.review_grading_id,
                )
            )
        )

        if disease_id:
            base = base.filter(GradingTask.disease_id == disease_id)
        if lab_unit_id:
            base = base.filter(GradingTask.lab_unit_id == lab_unit_id)
        if state:
            base = base.filter(GradingTask.state == state)

        rows = base.order_by(GradingTask.id.desc()).limit(200).all()

    return render_template(
        "admin/task_review_inconsistency.html",
        rows=rows,
        diseases=diseases,
        lab_units=lab_units,
        selected_disease_id=disease_id,
        selected_lab_unit_id=lab_unit_id,
        selected_state=state,
    )


@roles_required("admin")
@login_required
def apply_review_as_final(task_id: int):
    """Apply latest review grade as consensus for a task."""
    with transaction_scope() as db:
        latest_review = _latest_review_subquery()
        row = (
            db.query(
                GradingTask,
                latest_review.c.review_grading_id,
                latest_review.c.review_impression,
                latest_review.c.review_grade_id,
            )
            .join(latest_review, latest_review.c.task_id == GradingTask.id)
            .filter(latest_review.c.rn == 1)
            .filter(GradingTask.id == task_id)
            .first()
        )

        if not row:
            flash("Task or review grade not found.", "error")
            return redirect(url_for("admin.task_review_inconsistency"))

        task: GradingTask = row[0]
        review_grading_id = row.review_grading_id
        review_impression = row.review_impression

        grading = db.get(DiseaseGrading, review_grading_id) if review_grading_id else None
        if not grading:
            flash("Latest review grading is missing; cannot apply.", "error")
            return redirect(url_for("admin.task_review_inconsistency"))

        consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        if not consensus:
            consensus = Consensus(task_id=task_id)
            db.add(consensus)

        consensus.final_disease_grading_id = review_grading_id
        consensus.method = "task_review"
        consensus.decided_by_user_id = current_user.id
        consensus.decided_at = datetime.now(timezone.utc)
        consensus.final_disease_name = grading.disease.name if grading.disease else None
        consensus.final_grade_name = grading.impression
        consensus.final_grade_description = grading.guidelines

        # Optionally bring task to final if it's not already
        if task.state != "final":
            task.state = "final"

        db.flush()
        flash(f"Applied review grade '{review_impression}' as final consensus for task {task_id}.", "success")

    return redirect(url_for("admin.task_review_inconsistency"))
