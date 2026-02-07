from __future__ import annotations

from typing import List

from flask import render_template, request
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import Disease, GradingTask, LabUnit, RegradeTask, Role, User, user_lab_units
from utils.hospital_scoping import apply_scoping


def register_routes(bp) -> None:
    bp.add_url_rule("/regrade-tasks", view_func=regrade_tasks, methods=["GET"])


@roles_required("regrade_adjudicator", "admin", "local_admin")
def regrade_tasks():
    with get_db_session() as db:
        lu_query = select(LabUnit).order_by(LabUnit.hospital_id, LabUnit.name)
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
        lab_units = db.execute(lu_query).scalars().all()
        allowed_lab_unit_ids = {lu.id for lu in lab_units}

        diseases = db.query(Disease).order_by(Disease.name).all()

        regrade_adjudicators: List[User] = []
        if allowed_lab_unit_ids:
            regrade_query = (
                select(User)
                .join(User.roles)
                .join(user_lab_units, user_lab_units.c.user_id == User.id)
                .where(Role.name == "regrade_adjudicator")
                .where(user_lab_units.c.lab_unit_id.in_(allowed_lab_unit_ids))
                .order_by(User.username)
                .distinct()
            )
            regrade_adjudicators = db.execute(regrade_query).scalars().all()

        disease_id = request.args.get("disease_id", type=int)
        lab_unit_id = request.args.get("lab_unit_id", type=int)
        status = request.args.get("status", type=str)
        assigned_to_user_id = request.args.get("assigned_to_user_id", type=int)

        query = (
            select(RegradeTask)
            .options(
                selectinload(RegradeTask.source_task)
                .selectinload(GradingTask.encounter_file),
                selectinload(RegradeTask.source_task)
                .selectinload(GradingTask.direct_image),
                selectinload(RegradeTask.source_task)
                .selectinload(GradingTask.patient_encounter),
                selectinload(RegradeTask.disease),
                selectinload(RegradeTask.lab_unit),
                selectinload(RegradeTask.assigned_to),
                selectinload(RegradeTask.created_by),
            )
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .order_by(RegradeTask.status.asc(), RegradeTask.created_at.desc())
        )

        if disease_id:
            query = query.where(RegradeTask.disease_id == disease_id)
        if lab_unit_id and lab_unit_id in allowed_lab_unit_ids:
            query = query.where(RegradeTask.lab_unit_id == lab_unit_id)
        if status in {"regrade_pending", "regrade_done"}:
            query = query.where(RegradeTask.status == status)

        is_admin = current_user.has_role("admin", "local_admin")
        if is_admin and assigned_to_user_id:
            query = query.where(RegradeTask.assigned_to_user_id == assigned_to_user_id)
        elif not is_admin:
            query = query.where(RegradeTask.assigned_to_user_id == current_user.id)

        tasks = db.execute(query).scalars().all()

        return render_template(
            "grading/regrade_tasks.html",
            tasks=tasks,
            lab_units=lab_units,
            diseases=diseases,
            regrade_adjudicators=regrade_adjudicators,
            filters={
                "disease_id": disease_id,
                "lab_unit_id": lab_unit_id,
                "status": status,
                "assigned_to_user_id": assigned_to_user_id,
            },
            is_admin=is_admin,
        )
