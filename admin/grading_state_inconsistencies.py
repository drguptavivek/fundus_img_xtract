from __future__ import annotations

from typing import Any, Dict, List, Sequence

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import and_, exists

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import Disease, Grade, GradingTask, LabUnit


@roles_required("admin")
def grading_state_inconsistencies():
    """
    Admin view to surface grading-task inconsistencies and allow remediation.

    Focus: tasks that have a Resident2 grade but are missing a Resident grade,
    leaving them stuck in resident2_done. Resetting moves them to pending so
    Resident grading can proceed; once Resident grades, the normal flow resumes:
      - Resident + Resident2 match -> state becomes final
      - Resident + Resident2 mismatch -> state becomes arbitration
    """
    with transaction_scope() as db:
        if request.method == "POST":
            task_ids = request.form.getlist("task_id")
            cleaned_ids = [int(tid) for tid in task_ids if tid.isdigit()]
            if cleaned_ids:
                updated = (
                    db.query(GradingTask)
                    .filter(
                        GradingTask.id.in_(cleaned_ids),
                        GradingTask.state == "resident2_done",
                    )
                    .update({GradingTask.state: "pending"}, synchronize_session=False)
                )
                db.commit()
                flash(f"Reset {updated} task(s) to pending for Resident grading.", "success")
            else:
                flash("No tasks selected to reset.", "warning")
            return redirect(url_for("admin.grading_state_inconsistencies"))

        # Detect tasks with Resident2 grade present but Resident grade missing
        resident2_exists = (
            db.query(Grade.task_id)
            .filter(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"))
        )
        resident_missing = ~exists().where(
            and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident")
        )

        rows: Sequence[Any] = (
            db.query(
                GradingTask.id,
                GradingTask.state,
                Disease.name.label("disease_name"),
                LabUnit.name.label("lab_unit_name"),
                LabUnit.id.label("lab_unit_id"),
                GradingTask.encounter_file_id,
                GradingTask.direct_image_upload_id,
            )
            .join(Disease, Disease.id == GradingTask.disease_id)
            .join(LabUnit, LabUnit.id == GradingTask.lab_unit_id)
            .filter(GradingTask.state == "resident2_done")
            .filter(resident_missing)
            .filter(resident2_exists.exists())
            .order_by(Disease.name, GradingTask.id.desc())
            .all()
        )

        # Map rows into template-friendly objects grouped by disease
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row.disease_name, []).append(
                {
                    "id": row.id,
                    "state": row.state,
                    "lab_unit_name": row.lab_unit_name,
                    "lab_unit_id": row.lab_unit_id,
                    "encounter_file_id": row.encounter_file_id,
                    "direct_image_upload_id": row.direct_image_upload_id,
                }
            )

        return render_template(
            "admin/grading_inconsistencies.html",
            grouped=grouped,
            total=len(rows),
            current_user=current_user,
        )
