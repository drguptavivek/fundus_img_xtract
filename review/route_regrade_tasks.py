from __future__ import annotations

from typing import List

from flask import flash, redirect, request, url_for
from flask_login import current_user
import sqlalchemy as sa
from sqlalchemy import select, text

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import LabUnit, RegradeTask, Role, User, user_lab_units
from utils.discrepancy_filters import build_discrepancy_filter_query
from utils.final_grade_basis import normalize_final_grade_basis
from utils.hospital_scoping import apply_scoping
from . import bp
from .route_discrepancy_review import render_discrepancy_review
from .task_review import AI_REVIEW_STATUS_LABELS


@bp.route("/regrade-tasks", methods=["POST"])
@roles_required("admin", "local_admin")
def create_regrade_tasks():
    with transaction_scope() as db:
        lu_query = sa.select(LabUnit)
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
        allowed_lab_units = db.execute(lu_query).scalars().all()
        allowed_lab_unit_ids = {lu.id for lu in allowed_lab_units}
        if not allowed_lab_unit_ids:
            flash("No lab units available for regrade queue creation.", "error")
            return redirect(url_for("review.discrepancy_review"))

        disease_id = request.form.get("disease_id", type=int)
        if not disease_id:
            flash("Disease selection is required for regrade queue creation.", "error")
            return redirect(url_for("review.discrepancy_review"))

        assigned_to_user_id = request.form.get("assigned_to_user_id", type=int)
        if not assigned_to_user_id:
            flash("Regrade adjudicator is required.", "error")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        notes = (request.form.get("regrade_notes") or "").strip()
        if not notes:
            flash("Regrade notes are required.", "error")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        assigned_user = (
            db.query(User)
            .join(User.roles)
            .filter(User.id == assigned_to_user_id, Role.name == "regrade_adjudicator")
            .first()
        )
        if not assigned_user:
            flash("Selected user is not a regrade adjudicator.", "error")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        assigned_lab_unit_ids = {
            row.lab_unit_id
            for row in db.execute(
                select(user_lab_units.c.lab_unit_id).where(user_lab_units.c.user_id == assigned_to_user_id)
            ).all()
        }

        lab_unit_id = request.form.get("lab_unit_id", type=int)
        if lab_unit_id and lab_unit_id not in allowed_lab_unit_ids:
            flash("You are not allowed to create regrades for this lab unit.", "error")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        has_arbitrator = request.form.get("has_arbitrator", type=str)
        if has_arbitrator is None:
            has_arbitrator = "yes"

        resident_compare = request.form.get("resident_compare", type=str)
        if resident_compare is None:
            resident_compare = "mismatch"

        has_regrade = request.form.get("has_regrade", type=str)
        if has_regrade is None:
            has_regrade = "no"

        filters = {
            "disease_id": disease_id,
            "lab_unit_id": lab_unit_id,
            "resident_grade": request.form.getlist("resident_grade"),
            "resident2_grade": request.form.getlist("resident2_grade"),
            "arbitrator_grade": request.form.getlist("arbitrator_grade"),
            "final_grade": request.form.getlist("final_grade"),
            "has_ai_grade": request.form.get("has_ai_grade", type=str),
            "has_review": request.form.get("has_review", type=str),
            "has_arbitrator": has_arbitrator,
            "review_grade": request.form.getlist("review_grade"),
            "has_consensus": request.form.get("has_consensus", type=str),
            "consensus_method": request.form.get("consensus_method", type=str),
            "resident_compare": resident_compare,
            "ai_model_id": request.form.getlist("ai_model_id"),
            "ai_grade": request.form.getlist("ai_grade"),
            "ai_review_status": [
                status
                for status in request.form.getlist("ai_review_status")
                if status in AI_REVIEW_STATUS_LABELS
            ],
            "final_grade_basis": normalize_final_grade_basis(request.form.get("final_grade_basis")),
            "has_regrade": has_regrade,
            "regrade_grade": request.form.getlist("regrade_grade"),
            "allowed_lab_units": list(allowed_lab_unit_ids),
        }

        mv_name, where_sql, params, _selected_ai_model_id = build_discrepancy_filter_query(db, filters)
        if not mv_name:
            flash("No tasks matched the filters for regrade queue creation.", "warning")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        task_sql = f"""
            SELECT v.task_id, v.task_lab_unit_id
            FROM {mv_name} v
            WHERE {where_sql}
        """
        rows = db.execute(text(task_sql), params).fetchall()
        if not rows:
            flash("No tasks matched the filters for regrade queue creation.", "warning")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        task_lab_unit_ids = {row.task_lab_unit_id for row in rows}
        if not task_lab_unit_ids.issubset(assigned_lab_unit_ids):
            flash("Selected adjudicator is not assigned to all task lab units.", "error")
            return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))

        task_ids = [row.task_id for row in rows]
        existing = {
            row.source_task_id
            for row in db.query(RegradeTask.source_task_id)
            .filter(
                RegradeTask.status == "regrade_pending",
                RegradeTask.source_task_id.in_(task_ids),
            )
            .all()
        }

        created = 0
        for row in rows:
            if row.task_id in existing:
                continue
            db.add(
                RegradeTask(
                    source_task_id=row.task_id,
                    disease_id=disease_id,
                    lab_unit_id=row.task_lab_unit_id,
                    assigned_to_user_id=assigned_to_user_id,
                    created_by_user_id=current_user.id,
                    status="regrade_pending",
                    notes=notes,
                )
            )
            created += 1

        skipped = len(task_ids) - created
        flash(
            f"Regrade tasks created: {created}. Skipped existing pending: {skipped}.",
            "success" if created else "warning",
        )
        return redirect(request.referrer or url_for("review.discrepancy_review", disease_id=disease_id))


@bp.route("/regrade-task-creator", methods=["GET"])
@roles_required("admin", "local_admin")
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
