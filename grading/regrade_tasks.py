from __future__ import annotations

import json
import logging
from datetime import timedelta
from json import JSONDecodeError
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import (
    Consensus,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    GradingsFeatures,
    ImageMetadata,
    LabUnit,
    RegradeTask,
)
from utils.dualGradingFetchDetailUtils import fetch_existing_grade_for_user
from utils.hospital_scoping import apply_scoping
from utils.log_sanitize import sanitize_log_value
from utils.masterUtils import fetch_active_disease_gradings


regrade_logger = logging.getLogger("regrade_grading")


def _fetch_allowed_lab_units(db):
    lu_query = select(LabUnit).order_by(LabUnit.hospital_id, LabUnit.name)
    lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
    lab_units = db.execute(lu_query).scalars().all()
    allowed_lab_unit_ids = {lu.id for lu in lab_units}
    return lab_units, allowed_lab_unit_ids


def _fetch_regrade_task(db, regrade_task_id: int, allowed_lab_unit_ids: set[int]):
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
    if allowed_lab_unit_ids:
        query = query.where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
    return db.execute(query).scalars().first()


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
    bp.add_url_rule("/regrade-task/<int:regrade_task_id>", view_func=regrade_task_detail, methods=["GET"])
    bp.add_url_rule(
        "/regrade-task/<int:regrade_task_id>/submit",
        view_func=regrade_task_submit,
        methods=["POST"],
    )


@roles_required("regrade_adjudicator", "admin", "local_admin")
def regrade_tasks():
    with transaction_scope() as db:
        lab_units, allowed_lab_unit_ids = _fetch_allowed_lab_units(db)
        diseases = db.query(Disease).order_by(Disease.name).all()

        is_admin = current_user.has_role("admin", "local_admin")
        pending_query = (
            select(RegradeTask.disease_id, func.count(RegradeTask.id))
            .where(RegradeTask.status == "regrade_pending")
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .group_by(RegradeTask.disease_id)
        )
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
                can_revise = (now - created_at) <= timedelta(hours=24)
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


@roles_required("regrade_adjudicator", "admin", "local_admin")
def start_random_regrade_task():
    with transaction_scope() as db:
        _lab_units, allowed_lab_unit_ids = _fetch_allowed_lab_units(db)
        if not allowed_lab_unit_ids:
            flash("No lab units available for regrade tasks.", "warning")
            return redirect(url_for("grading.regrade_tasks"))

        disease_id = request.args.get("disease_id", type=int)
        lab_unit_id = request.args.get("lab_unit_id", type=int)
        assigned_to_user_id = request.args.get("assigned_to_user_id", type=int)

        is_admin = current_user.has_role("admin", "local_admin")

        query = (
            select(RegradeTask.id)
            .where(RegradeTask.status == "regrade_pending")
            .where(RegradeTask.lab_unit_id.in_(allowed_lab_unit_ids))
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


@roles_required("regrade_adjudicator", "admin", "local_admin")
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

        is_admin = current_user.has_role("admin", "local_admin")
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
                    allow_revision = (utcnow() - existing_grade.created_at) <= timedelta(hours=24)

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
            allow_revision=allow_revision,
            current_user_id=getattr(current_user, "id", None),
            current_slot="regrade_adj",
            is_admin=is_admin,
        )


@roles_required("regrade_adjudicator", "admin", "local_admin")
def regrade_task_submit(regrade_task_id: int):
    if not regrade_task_id or regrade_task_id <= 0:
        flash("Invalid regrade task reference.", "danger")
        return redirect(url_for("grading.regrade_tasks"))

    label_id = request.form.get("label_id", type=int)
    comment = (request.form.get("comment") or "").strip() or None
    action = (request.form.get("action") or "").strip().lower()

    raw_selected_features = request.form.getlist("selected_features")
    selected_feature_ids: list[int] = []
    for raw_feature in raw_selected_features:
        if raw_feature in (None, ""):
            continue
        try:
            selected_feature_ids.append(int(raw_feature))
        except (TypeError, ValueError):
            flash("Invalid feature selection submitted.", "danger")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

    unique_feature_ids: list[int] = []
    seen_feature_ids: set[int] = set()
    for feature_id in selected_feature_ids:
        if feature_id not in seen_feature_ids:
            unique_feature_ids.append(feature_id)
            seen_feature_ids.add(feature_id)

    if not label_id or not isinstance(label_id, int) or label_id <= 0:
        flash("Invalid label ID.", "danger")
        return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

    with transaction_scope() as db:
        lab_units, allowed_lab_unit_ids = _fetch_allowed_lab_units(db)
        regrade_task = _fetch_regrade_task(db, regrade_task_id, allowed_lab_unit_ids)
        if not regrade_task:
            flash("Regrade task not found.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        is_admin = current_user.has_role("admin", "local_admin")
        if not is_admin and regrade_task.assigned_to_user_id != current_user.id:
            flash("You are not assigned to this regrade task.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        source_task = regrade_task.source_task
        if not source_task:
            flash("Source task not available for regrade.", "danger")
            return redirect(url_for("grading.regrade_tasks"))

        disease_gradings = fetch_active_disease_gradings(db, regrade_task.disease_id)
        if not disease_gradings:
            flash("No disease gradings available for this task.", "danger")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        label = next((dg for dg in disease_gradings if dg.id == label_id), None)
        if not label:
            flash("Invalid label.", "danger")
            return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        selected_features_json = None
        if unique_feature_ids:
            available_features = (
                db.query(GradingsFeatures)
                .filter(GradingsFeatures.disease_grading_id == label_id)
                .all()
            )
            features_by_id = {feature.id: feature for feature in available_features}
            invalid_features = [fid for fid in unique_feature_ids if fid not in features_by_id]
            if invalid_features:
                flash("One or more selected features are not valid for the chosen grade.", "danger")
                return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

            selected_feature_entities = sorted(
                (features_by_id[fid] for fid in unique_feature_ids),
                key=lambda feature: ((feature.sr_no or 0), feature.id),
            )
            selected_features_json = json.dumps(
                [
                    {
                        "id": feature.id,
                        "label": feature.label,
                        "sr_no": feature.sr_no,
                    }
                    for feature in selected_feature_entities
                ]
            )

        existing_grade = fetch_existing_grade_for_user(
            db,
            source_task.id,
            current_user.id,
            "regrade_adj",
            user=current_user,
        )
        if existing_grade and existing_grade.created_at:
            if (utcnow() - existing_grade.created_at) > timedelta(hours=24):
                flash("Revision window has closed (24 hours).", "warning")
                return redirect(url_for("grading.regrade_task_detail", regrade_task_id=regrade_task_id))

        disease_grading = db.query(DiseaseGrading).filter(DiseaseGrading.id == label_id).first()
        disease = None
        if disease_grading:
            disease = db.query(Disease).filter(Disease.id == disease_grading.disease_id).first()

        if existing_grade:
            existing_grade.disease_grading_id = label_id
            existing_grade.comment = comment
            existing_grade.selected_features_json = selected_features_json
            existing_grade.disease_name = disease.name if disease else None
            existing_grade.grade_name = disease_grading.impression if disease_grading else None
            existing_grade.grade_description = disease_grading.guidelines if disease_grading else None
            db.add(existing_grade)
            db.flush()
        else:
            new_grade = Grade(
                task_id=source_task.id,
                grader_user_id=current_user.id,
                role_slot="regrade_adj",
                disease_grading_id=label_id,
                comment=comment,
                selected_features_json=selected_features_json,
                disease_name=disease.name if disease else None,
                grade_name=disease_grading.impression if disease_grading else None,
                grade_description=disease_grading.guidelines if disease_grading else None,
            )
            db.add(new_grade)
            db.flush()

        consensus = db.query(Consensus).filter(Consensus.task_id == source_task.id).first()
        if consensus:
            consensus.final_disease_grading_id = label_id
            consensus.method = "regrade"
            consensus.decided_by_user_id = current_user.id
            consensus.decided_at = utcnow()
            consensus.final_disease_name = disease.name if disease else None
            consensus.final_grade_name = disease_grading.impression if disease_grading else None
            consensus.final_grade_description = disease_grading.guidelines if disease_grading else None
        else:
            consensus = Consensus(
                task_id=source_task.id,
                final_disease_grading_id=label_id,
                method="regrade",
                decided_by_user_id=current_user.id,
                decided_at=utcnow(),
                final_disease_name=disease.name if disease else None,
                final_grade_name=disease_grading.impression if disease_grading else None,
                final_grade_description=disease_grading.guidelines if disease_grading else None,
            )
            db.add(consensus)

        regrade_task.status = "regrade_done"

        regrade_logger.info(
            "Regrade submitted [regrade_task_id=%s] [task_id=%s] [user_id=%s] [label_id=%s] [comment=%s]",
            sanitize_log_value(regrade_task.id),
            sanitize_log_value(source_task.id),
            sanitize_log_value(current_user.id),
            sanitize_log_value(label_id),
            sanitize_log_value(comment or ""),
        )

        flash("Regrade submitted successfully.", "success")

        if action == "save_next":
            return redirect(url_for("grading.start_random_regrade_task"))

        return redirect(url_for("grading.regrade_tasks"))
