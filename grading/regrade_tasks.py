from __future__ import annotations

import json
import logging
from json import JSONDecodeError

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from encounter_sets.permissions import (
    project_task_capability_clause,
    user_has_task_capability,
)
from grading.workbench.revision_policy import REVISION_WINDOW
from grading_schemes.service import STANDARD_NON_GRADABLE_REASONS

REGRADE_ROLES = frozenset({"regrade_adjudicator"})
REGRADE_MANAGER_ROLES = frozenset({"data_manager"})
from authz.behaviors import role_lab_units
from models import (
    Disease,
    Grade,
    GradingTask,
    ImageMetadata,
    LabUnit,
    RegradeTask,
    Role,
    User,
    user_lab_units,
)
from project_annotations.service import (
    resolve_task_annotation_context,
)
from utils.dualGradingFetchDetailUtils import fetch_existing_grade_for_user
from utils.log_sanitize import sanitize_log_value
from utils.masterUtils import fetch_active_disease_gradings

regrade_logger = logging.getLogger("regrade_grading")


def _fetch_allowed_lab_units(db):
    lu_query = select(LabUnit).order_by(LabUnit.hospital_id, LabUnit.name)
    lu_query = role_lab_units(
        db,
        lu_query,
        current_user,
        lab_roles={"regrade_adjudicator"},
        project_roles={"regrade_adjudicator"},
        allow_admin=True,
    )
    lab_units = db.execute(lu_query).scalars().all()
    allowed_lab_unit_ids = {lu.id for lu in lab_units}
    return lab_units, allowed_lab_unit_ids


def _fetch_manager_lab_units(db):
    lu_query = select(LabUnit).order_by(LabUnit.hospital_id, LabUnit.name)
    lu_query = role_lab_units(
        db,
        lu_query,
        current_user,
        lab_roles=REGRADE_MANAGER_ROLES,
        hospital_roles=REGRADE_MANAGER_ROLES,
        project_roles=REGRADE_MANAGER_ROLES,
        allow_admin=True,
    )
    lab_units = db.execute(lu_query).scalars().all()
    return lab_units, {lab_unit.id for lab_unit in lab_units}


def _fetch_regrade_task(db, regrade_task_id: int, allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return None
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
        .where(RegradeTask.id == regrade_task_id)
    )
    query = query.where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
    row = db.execute(query).scalars().first()
    if row and not user_has_task_capability(
        db,
        user=current_user,
        task_id=row.source_task_id,
        roles=REGRADE_ROLES,
    ):
        return None
    return row


def _resolve_image_uuid(task: GradingTask | None) -> str | None:
    if not task:
        return None
    if task.encounter_file:
        return task.encounter_file.uuid
    if task.direct_image:
        return task.direct_image.uuid
    if task.patient_encounter:
        return task.patient_encounter.uuid
    return None


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


def _parse_selected_features(selected_features_json: str | None) -> list[dict[str, object] | str]:
    if not selected_features_json:
        return []
    try:
        parsed = json.loads(selected_features_json)
        if isinstance(parsed, list):
            return parsed
    except JSONDecodeError:
        regrade_logger.warning("Failed to parse selected features JSON", exc_info=True)
    return []


def register_routes(bp) -> None:
    bp.add_url_rule("/regrade-tasks", view_func=regrade_tasks, methods=["GET"])
    bp.add_url_rule("/regrade-tasks/random", view_func=start_random_regrade_task, methods=["GET"])
    bp.add_url_rule(
        "/regrade-tasks/reassign",
        view_func=regrade_tasks_reassign,
        methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/regrade-task/<int:regrade_task_id>",
        view_func=regrade_task_detail,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/regrade-task/<int:regrade_task_id>/reassign",
        view_func=regrade_task_reassign,
        methods=["POST"],
    )


@login_required
def regrade_tasks():
    with transaction_scope() as db:
        _lab_units, allowed_lab_unit_ids = _fetch_allowed_lab_units(db)
        diseases = db.query(Disease).order_by(Disease.name).all()

        is_admin = current_user.has_role("admin")
        pending_query = (
            select(RegradeTask.disease_id, func.count(RegradeTask.id))
            .where(RegradeTask.status == "regrade_pending")
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .group_by(RegradeTask.disease_id)
        )
        pending_query = pending_query.where(project_task_capability_clause(
            RegradeTask.source_task_id, current_user, REGRADE_ROLES
        ))
        if not is_admin:
            pending_query = pending_query.where(RegradeTask.assigned_to_user_id == current_user.id)

        pending_counts = dict(db.execute(pending_query).all())

        page = max(1, request.args.get("page", default=1, type=int) or 1)
        per_page = 50

        latest_regrade_subq = (
            select(
                RegradeTask.source_task_id.label("source_task_id"),
                func.max(RegradeTask.id).label("regrade_task_id"),
            )
            .group_by(RegradeTask.source_task_id)
            .subquery()
        )

        recent_total = db.execute(
            select(func.count(Grade.id))
            .join(latest_regrade_subq, latest_regrade_subq.c.source_task_id == Grade.task_id)
            .join(RegradeTask, RegradeTask.id == latest_regrade_subq.c.regrade_task_id)
            .where(Grade.grader_user_id == current_user.id)
            .where(Grade.role_slot == "regrade_adj")
            .where(project_task_capability_clause(
                RegradeTask.source_task_id, current_user, REGRADE_ROLES
            ))
        ).scalar() or 0

        total_pages = max(1, (recent_total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        recent_query = (
            select(Grade, RegradeTask)
            .join(latest_regrade_subq, latest_regrade_subq.c.source_task_id == Grade.task_id)
            .join(RegradeTask, RegradeTask.id == latest_regrade_subq.c.regrade_task_id)
            .where(Grade.grader_user_id == current_user.id)
            .where(Grade.role_slot == "regrade_adj")
            .where(project_task_capability_clause(
                RegradeTask.source_task_id, current_user, REGRADE_ROLES
            ))
            .order_by(Grade.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )

        recent_rows = db.execute(recent_query).all()
        recent_regrades = []
        now = utcnow()
        for grade, regrade_task in recent_rows:
            created_at = grade.created_at
            can_revise = True
            if created_at:
                can_revise = (now - created_at) < REVISION_WINDOW
            recent_regrades.append(
                {
                    "grade": grade,
                    "regrade_task": regrade_task,
                    "can_revise": can_revise,
                }
            )

        return render_template(
            "grading/regrade_tasks.html",
            diseases=diseases,
            is_admin=is_admin,
            pending_counts=pending_counts,
            recent_regrades=recent_regrades,
            recent_page=page,
            recent_total=recent_total,
            recent_total_pages=total_pages,
        )


@login_required
def regrade_tasks_reassign():
    with transaction_scope() as db:
        _lab_units, allowed_lab_unit_ids = _fetch_manager_lab_units(db)
        if not allowed_lab_unit_ids:
            flash("No lab units available for regrade tasks.", "warning")
            return redirect(url_for("grading.regrade_tasks"))

        assignee_id_raw = request.args.get("assignee_id", default="", type=str)
        assignee_id = None
        if assignee_id_raw and assignee_id_raw != "unassigned":
            try:
                assignee_id = int(assignee_id_raw)
            except ValueError:
                assignee_id = None

        counts_query = (
            select(RegradeTask.assigned_to_user_id, func.count(RegradeTask.id))
            .where(RegradeTask.status == "regrade_pending")
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .group_by(RegradeTask.assigned_to_user_id)
            .order_by(func.count(RegradeTask.id).desc())
        )
        counts_query = counts_query.where(project_task_capability_clause(
            RegradeTask.source_task_id, current_user, REGRADE_MANAGER_ROLES
        ))
        assignee_counts = db.execute(counts_query).all()
        total_pending = sum(row[1] for row in assignee_counts)
        unassigned_count = sum(row[1] for row in assignee_counts if row[0] is None)
        assignee_ids = [row[0] for row in assignee_counts if row[0] is not None]

        users = []
        if assignee_ids:
            users = (
                db.query(User)
                .filter(User.id.in_(assignee_ids))
                .order_by(User.username)
                .all()
            )
        users_by_id = {u.id: u for u in users}

        tasks_query = (
            select(RegradeTask)
            .options(
                selectinload(RegradeTask.source_task),
                selectinload(RegradeTask.disease),
                selectinload(RegradeTask.lab_unit),
                selectinload(RegradeTask.assigned_to),
            )
            .where(RegradeTask.status == "regrade_pending")
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .order_by(RegradeTask.id.desc())
        )
        tasks_query = tasks_query.where(project_task_capability_clause(
            RegradeTask.source_task_id, current_user, REGRADE_MANAGER_ROLES
        ))
        if assignee_id_raw == "unassigned":
            tasks_query = tasks_query.where(RegradeTask.assigned_to_user_id.is_(None))
        elif assignee_id is not None:
            tasks_query = tasks_query.where(RegradeTask.assigned_to_user_id == assignee_id)

        tasks = db.execute(tasks_query).scalars().all()
        task_lab_unit_ids = {task.lab_unit_id for task in tasks if task.lab_unit_id}

        target_users: list[User] = []
        if task_lab_unit_ids:
            target_users_query = select(User).where(User.is_active.is_(True))
            candidates = db.execute(target_users_query).scalars().all()
            target_users = [
                user for user in candidates
                if all(
                    user_has_task_capability(
                        db, user=user, task_id=task.source_task_id, roles=REGRADE_ROLES
                    )
                    for task in tasks
                )
            ]
            target_users.sort(key=lambda user: user.username)

        if request.method == "POST":
            task_ids = request.form.getlist("task_ids")
            target_user_id = request.form.get("target_user_id", type=int)
            if not task_ids:
                flash("Select at least one regrade task to reassign.", "warning")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))
            if not target_user_id:
                flash("Select a target regrade adjudicator.", "warning")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            task_ids_int: list[int] = []
            for raw_id in task_ids:
                try:
                    task_ids_int.append(int(raw_id))
                except (TypeError, ValueError):
                    flash("Invalid regrade task selection.", "danger")
                    return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            if len(set(task_ids_int)) != len(task_ids_int):
                flash("Invalid regrade task selection.", "danger")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            tasks_to_update = (
                db.query(RegradeTask)
                .filter(RegradeTask.id.in_(task_ids_int))
                .filter(RegradeTask.status == "regrade_pending")
                .filter(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
                .filter(project_task_capability_clause(
                    RegradeTask.source_task_id, current_user, REGRADE_MANAGER_ROLES
                ))
                .all()
            )
            if not tasks_to_update:
                flash("No eligible regrade tasks found for reassignment.", "warning")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            if {task.id for task in tasks_to_update} != set(task_ids_int):
                flash("One or more selected regrade tasks are outside your scope.", "danger")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            target_user = db.query(User).filter(
                User.id == target_user_id,
                User.is_active.is_(True),
            ).first()
            if not target_user:
                flash("Selected user is not a valid regrade adjudicator.", "danger")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            if any(
                not user_has_task_capability(
                    db,
                    user=target_user,
                    task_id=task.source_task_id,
                    roles=REGRADE_ROLES,
                )
                for task in tasks_to_update
            ):
                flash("Target user lacks project regrade access for one or more tasks.", "danger")
                return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

            for task in tasks_to_update:
                task.assigned_to_user_id = target_user_id

            regrade_logger.info(
                "Bulk regrade reassigned [task_count=%s] [to_user_id=%s]",
                sanitize_log_value(len(tasks_to_update)),
                sanitize_log_value(target_user_id),
            )

            flash(f"Reassigned {len(tasks_to_update)} regrade task(s).", "success")
            return redirect(url_for("grading.regrade_tasks_reassign", assignee_id=assignee_id_raw))

        return render_template(
            "grading/regrade_tasks_reassign.html",
            assignee_counts=assignee_counts,
            users_by_id=users_by_id,
            selected_assignee_id=assignee_id_raw,
            tasks=tasks,
            target_users=target_users,
            total_pending=total_pending,
            unassigned_count=unassigned_count,
        )


@login_required
def start_random_regrade_task():
    with transaction_scope() as db:
        _lab_units, allowed_lab_unit_ids = _fetch_allowed_lab_units(db)
        if not allowed_lab_unit_ids:
            flash("No lab units available for regrade tasks.", "warning")
            return redirect(url_for("grading.regrade_tasks"))

        disease_id = request.args.get("disease_id", type=int)
        lab_unit_id = request.args.get("lab_unit_id", type=int)
        assigned_to_user_id = request.args.get("assigned_to_user_id", type=int)

        is_admin = current_user.has_role("admin")

        query = (
            select(RegradeTask.id)
            .where(RegradeTask.status == "regrade_pending")
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .where(project_task_capability_clause(
                RegradeTask.source_task_id, current_user, REGRADE_ROLES
            ))
        )
        if disease_id:
            query = query.where(RegradeTask.disease_id == disease_id)
        if lab_unit_id and lab_unit_id in allowed_lab_unit_ids:
            query = query.where(RegradeTask.lab_unit_id == lab_unit_id)
        if is_admin and assigned_to_user_id:
            query = query.where(RegradeTask.assigned_to_user_id == assigned_to_user_id)
        elif not is_admin:
            query = query.where(RegradeTask.assigned_to_user_id == current_user.id)

        regrade_task_id = db.execute(query.order_by(func.random()).limit(1)).scalar()
        if not regrade_task_id:
            flash("No pending regrade tasks found for the selected filters.", "info")
            return redirect(
                url_for(
                    "grading.regrade_tasks",
                    disease_id=disease_id,
                    lab_unit_id=lab_unit_id,
                    assigned_to_user_id=assigned_to_user_id,
                )
            )

        return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))


@login_required
def regrade_task_detail(regrade_task_id: int):
    if not regrade_task_id or regrade_task_id <= 0:
        flash("Invalid regrade task reference.", "danger")
        return redirect(url_for("grading.regrade_tasks"))

    with transaction_scope() as db:
        _lab_units, allowed_lab_unit_ids = _fetch_allowed_lab_units(db)
        regrade_task = _fetch_regrade_task(db, regrade_task_id, allowed_lab_unit_ids)
        if not regrade_task:
            flash("Regrade task not found.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        is_admin = current_user.has_role("admin")
        if not is_admin and regrade_task.assigned_to_user_id != current_user.id:
            flash("You are not assigned to this regrade task.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        disease_gradings = fetch_active_disease_gradings(db, regrade_task.disease_id)
        if not disease_gradings:
            flash("No disease gradings available for this task.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        grading_guidelines = {grading.id: grading.guidelines for grading in disease_gradings}
        grading_features = []
        for grading in disease_gradings:
            sorted_features = sorted(
                grading.features or [],
                key=lambda feature: ((feature.sr_no or 0), feature.id),
            )
            grading_features.append(
                {
                    "id": grading.id,
                    "impression": grading.impression,
                    "display_order": grading.display_order,
                    "is_ungradable": bool(grading.is_ungradable),
                    "guidelines": grading.guidelines,
                    "features": [
                        {
                            "id": feature.id,
                            "sr_no": feature.sr_no,
                            "label": feature.label,
                        }
                        for feature in sorted_features
                    ],
                }
            )

        source_task = regrade_task.source_task
        image_uuid = _resolve_image_uuid(source_task)
        image_metadata = _fetch_image_metadata(db, image_uuid)

        regrade_adjudicators: list[User] = []
        if is_admin:
            regrade_query = (
                select(User)
                .join(User.roles)
                .join(user_lab_units, user_lab_units.c.user_id == User.id)
                .where(Role.name == "regrade_adjudicator")
                .where(User.is_active.is_(True))
                .where(user_lab_units.c.lab_unit_id == regrade_task.lab_unit_id)
                .order_by(User.username)
                .distinct()
            )
            regrade_adjudicators = db.execute(regrade_query).scalars().all()

        existing_grade = None
        existing_selected_features = []
        allow_revision = True
        if source_task:
            existing_grade = fetch_existing_grade_for_user(
                db,
                source_task.id,
                current_user.id,
                "regrade_adj",
                user=current_user,
            )
            if existing_grade:
                existing_selected_features = _parse_selected_features(existing_grade.selected_features_json)
                if existing_grade.created_at:
                    allow_revision = (utcnow() - existing_grade.created_at) < REVISION_WINDOW

        return render_template(
            "grading/regrade_task_detail.html",
            regrade_task=regrade_task,
            source_task=source_task,
            image_uuid=image_uuid,
            image_metadata=image_metadata,
            disease_gradings=disease_gradings,
            grading_guidelines=grading_guidelines,
            grading_features=grading_features,
            existing_grade=existing_grade,
            existing_selected_features=existing_selected_features,
            existing_feature_geometry=existing_grade.feature_geometry_json if existing_grade else None,
            allow_revision=allow_revision,
            current_user_id=getattr(current_user, "id", None),
            current_slot="regrade_adj",
            non_gradable_reasons=list(STANDARD_NON_GRADABLE_REASONS),
            is_admin=is_admin,
            regrade_adjudicators=regrade_adjudicators,
            annotation_context=resolve_task_annotation_context(db, source_task).to_dict(),
        )


@login_required
def regrade_task_reassign(regrade_task_id: int):
    if not regrade_task_id or regrade_task_id <= 0:
        flash("Invalid regrade task reference.", "danger")
        return redirect(url_for("grading.regrade_tasks"))

    assigned_to_user_id = request.form.get("assigned_to_user_id", type=int)
    if not assigned_to_user_id:
        flash("Regrade adjudicator is required.", "danger")
        return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

    with transaction_scope() as db:
        _lab_units, allowed_lab_unit_ids = _fetch_manager_lab_units(db)
        regrade_task = _fetch_regrade_task(db, regrade_task_id, allowed_lab_unit_ids)
        if not regrade_task:
            flash("Regrade task not found.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        if not user_has_task_capability(
            db,
            user=current_user,
            task_id=regrade_task.source_task_id,
            roles=REGRADE_MANAGER_ROLES,
        ):
            flash("Regrade task not found.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        if regrade_task.status != "regrade_pending":
            flash("Only pending regrade tasks can be reassigned.", "warning")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        eligible_user = db.query(User).filter(
            User.id == assigned_to_user_id,
            User.is_active.is_(True),
        ).first()
        if not eligible_user:
            flash("Selected user is not a valid regrade adjudicator for this lab unit.", "danger")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        if not user_has_task_capability(
            db,
            user=eligible_user,
            task_id=regrade_task.source_task_id,
            roles=REGRADE_ROLES,
        ):
            flash("Selected user lacks regrade access for this task.", "danger")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        if regrade_task.assigned_to_user_id == assigned_to_user_id:
            flash("Regrade task is already assigned to that user.", "info")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        previous_assignee_id = regrade_task.assigned_to_user_id
        regrade_task.assigned_to_user_id = assigned_to_user_id

        regrade_logger.info(
            "Regrade reassigned [regrade_task_id=%s] [from_user_id=%s] [to_user_id=%s]",
            sanitize_log_value(regrade_task.id),
            sanitize_log_value(previous_assignee_id),
            sanitize_log_value(assigned_to_user_id),
        )

        flash("Regrade task reassigned successfully.", "success")
        return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))
