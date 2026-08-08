"""Package-based EncounterSet grading views."""
from __future__ import annotations

import logging

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from markupsafe import Markup
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from grading.grade_feature_submission import (
    GradeFeatureValidationError,
    parse_selected_features,
    prepare_grade_feature_submission,
    serialize_grade_features,
)
from grading_schemes.service import STANDARD_NON_GRADABLE_REASONS, sanitize_guidelines_html
from models import DiseaseGrading, EncounterSetGradingPackage, Grade, GradingTask
from utils.dualGradingConsensusUtils import update_task_state_based_on_grades
from utils.dualGradingEligibility import get_user_eligibility_for_task, has_user_graded_task
from utils.dualGradingStuckTaskCleanup import cleanup_task_tracker

logger = logging.getLogger("grading.encounter_set_package")


def register_routes(bp):
    bp.add_url_rule(
        "/encounter_set_package/<string:package_uuid>/<string:slot_type>",
        view_func=encounter_set_package_grading,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/encounter_set_package/submit",
        view_func=encounter_set_package_submit,
        methods=["POST"],
    )


@login_required
@roles_required("resident", "resident2", "ophthalmologist", "arbitrator", "admin")
def encounter_set_package_grading(package_uuid: str, slot_type: str):
    if slot_type not in {"resident", "resident2", "arbitrator"}:
        flash("Invalid grading slot.", "danger")
        return redirect(url_for("grading.index"))

    with transaction_scope() as db:
        package = _fetch_package(db, package_uuid)
        if not package:
            flash("EncounterSet grading package not found.", "danger")
            return redirect(url_for("grading.index"))

        tasks = _ordered_package_tasks(package)
        task_panels = [_task_panel(db, task, slot_type) for task in tasks]
        if not any(panel["available"] for panel in task_panels):
            flash("No targets in this package are available for your grading slot.", "info")
            return redirect(url_for("grading.index"))

        first_available_index = next(
            index for index, panel in enumerate(task_panels) if panel["available"]
        )
        return render_template(
            "grading/encounter_set_package_grading.html",
            package=package,
            encounter=package.patient_encounter,
            tasks=tasks,
            task_panels=task_panels,
            first_available_index=first_available_index,
            slot_type=slot_type,
            current_user_id=current_user.id,
            non_gradable_reasons=list(STANDARD_NON_GRADABLE_REASONS),
            package_grading_data={
                panel["task"].uuid: {
                    "features": panel["grading_features"],
                    "existingSelectedFeatures": panel["existing_selected_features"],
                    "existingFeatureGeometry": (
                        panel["existing_grade"].feature_geometry_json
                        if panel["existing_grade"]
                        else None
                    ),
                    "readOnly": not panel["available"],
                    "taskUuid": panel["task"].uuid,
                }
                for panel in task_panels
            },
        )


@login_required
@roles_required("resident", "resident2", "ophthalmologist", "arbitrator", "admin")
def encounter_set_package_submit():
    package_uuid = request.form.get("package_uuid")
    slot_type = request.form.get("slot")
    if not package_uuid or slot_type not in {"resident", "resident2", "arbitrator"}:
        flash("Invalid EncounterSet package submission.", "danger")
        return redirect(url_for("grading.index"))

    with transaction_scope() as db:
        package = _fetch_package(db, package_uuid, for_update=True)
        if not package:
            flash("EncounterSet grading package not found.", "danger")
            return redirect(url_for("grading.index"))

        submissions = []
        for task in _ordered_package_tasks(package):
            if not _task_available_for_slot(task, slot_type):
                continue
            if not get_user_eligibility_for_task(db, current_user.id, task.id, slot_type):
                continue
            if slot_type in {"resident", "resident2"}:
                conflicting_slots = ["resident2"] if slot_type == "resident" else ["resident"]
                if has_user_graded_task(db, current_user.id, task.id, conflicting_slots):
                    continue

            label_id = _int_form_value(f"label_id_{task.uuid}")
            if not label_id:
                flash("Please select a grade for every available package target.", "warning")
                return redirect(url_for("grading.encounter_set_package_grading", package_uuid=package_uuid, slot_type=slot_type))

            label = (
                db.query(DiseaseGrading)
                .filter(
                    DiseaseGrading.id == label_id,
                    DiseaseGrading.disease_id == task.disease_id,
                    DiseaseGrading.is_active.is_(True),
                )
                .first()
            )
            if not label:
                flash("Invalid grade selected for one package target.", "danger")
                return redirect(url_for("grading.encounter_set_package_grading", package_uuid=package_uuid, slot_type=slot_type))

            existing_grade = (
                db.query(Grade)
                .filter(
                    Grade.task_id == task.id,
                    Grade.grader_user_id == current_user.id,
                    Grade.role_slot == slot_type,
                )
                .first()
            )
            comment = request.form.get(f"comment_{task.uuid}", "")
            try:
                feature_submission = prepare_grade_feature_submission(
                    db,
                    task=task,
                    label_id=label_id,
                    raw_selected_features=request.form.getlist(
                        f"selected_features_{task.uuid}"
                    ),
                    raw_feature_geometry=request.form.get(
                        f"feature_geometry_json_{task.uuid}"
                    ),
                    existing_grade=existing_grade,
                )
            except GradeFeatureValidationError as exc:
                flash(str(exc), "danger")
                return redirect(
                    url_for(
                        "grading.encounter_set_package_grading",
                        package_uuid=package_uuid,
                        slot_type=slot_type,
                    )
                )

            submissions.append(
                (task, label_id, existing_grade, comment, feature_submission)
            )

        if not submissions:
            flash("No package targets were updated.", "warning")
            return redirect(
                url_for(
                    "grading.encounter_set_package_grading",
                    package_uuid=package_uuid,
                    slot_type=slot_type,
                )
            )

        for task, label_id, existing_grade, comment, feature_submission in submissions:
            now = utcnow()
            if existing_grade:
                existing_grade.disease_grading_id = label_id
                existing_grade.comment = comment
                existing_grade.selected_features_json = (
                    feature_submission.selected_features_json
                )
                existing_grade.feature_geometry_json = (
                    feature_submission.feature_geometry_json
                )
                existing_grade.updated_at = now
            else:
                db.add(
                    Grade(
                        task_id=task.id,
                        grader_user_id=current_user.id,
                        role_slot=slot_type,
                        disease_grading_id=label_id,
                        comment=comment,
                        selected_features_json=feature_submission.selected_features_json,
                        feature_geometry_json=feature_submission.feature_geometry_json,
                        created_at=now,
                    )
                )
            db.flush()
            update_task_state_based_on_grades(task.id, db)
            cleanup_task_tracker(task.id, current_user.id, slot_type, db)

        _sync_package_state(package)
        flash(f"Submitted {len(submissions)} target grade(s) for {package.name}.", "success")
        return redirect(url_for("grading.index"))


def _fetch_package(db, package_uuid: str, *, for_update: bool = False) -> EncounterSetGradingPackage | None:
    query = (
        db.query(EncounterSetGradingPackage)
        .options(
            selectinload(EncounterSetGradingPackage.patient_encounter),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.disease),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.encounter_set_image),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.grades).selectinload(Grade.label),
        )
        .filter(EncounterSetGradingPackage.uuid == package_uuid)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def _ordered_package_tasks(package: EncounterSetGradingPackage) -> list[GradingTask]:
    return sorted(
        [task for task in package.tasks if task.state != "final" or task.grades],
        key=lambda task: (
            1 if task.grading_target_level == "encounter" else 0,
            _task_laterality_order(task),
            task.encounter_set_image.spatial_position if task.encounter_set_image else 0,
            task.disease.name if task.disease else "",
            task.id,
        ),
    )


def _task_laterality_order(task: GradingTask) -> int:
    image = task.encounter_set_image
    metadata = image.metadata_json if image and image.metadata_json else {}
    raw_value = metadata.get("laterality") or metadata.get("eye")
    value = str(raw_value or "").strip().lower()
    if value in {"od", "right", "right eye", "r"}:
        return 0
    if value in {"os", "left", "left eye", "l"}:
        return 1
    return 2


def _task_panel(db, task: GradingTask, slot_type: str) -> dict:
    labels = (
        db.query(DiseaseGrading)
        .options(selectinload(DiseaseGrading.features))
        .filter(DiseaseGrading.disease_id == task.disease_id, DiseaseGrading.is_active.is_(True))
        .order_by(DiseaseGrading.display_order)
        .all()
    )
    existing = next(
        (
            grade for grade in task.grades
            if grade.grader_user_id == current_user.id and grade.role_slot == slot_type
        ),
        None,
    )
    state_available = _task_available_for_slot(task, slot_type)
    allocated = state_available and get_user_eligibility_for_task(
        db,
        current_user.id,
        task.id,
        slot_type,
    )
    if not state_available:
        unavailable_reason = "Not available at this grading stage"
    elif not allocated:
        unavailable_reason = "Not allocated to you"
    else:
        unavailable_reason = None
    return {
        "task": task,
        "labels": labels,
        "guideline_html_by_label_id": {
            label.id: Markup(sanitize_guidelines_html(label.guidelines) or "")
            for label in labels
        },
        "grading_features": serialize_grade_features(labels),
        "existing_selected_features": parse_selected_features(
            existing.selected_features_json if existing else None
        ),
        "existing_grade": existing,
        "available": allocated,
        "unavailable_reason": unavailable_reason,
    }


def _task_available_for_slot(task: GradingTask, slot_type: str) -> bool:
    if slot_type == "resident":
        return task.state in {"pending", "resident_done"}
    if slot_type == "resident2":
        return task.state in {"resident_done", "resident2_done", "arbitration"}
    if slot_type == "arbitrator":
        return task.state in {"arbitration", "final"}
    return False


def _sync_package_state(package: EncounterSetGradingPackage) -> None:
    task_states = {task.state for task in package.tasks}
    if not task_states:
        return
    if "arbitration" in task_states:
        package.state = "arbitration"
    elif task_states == {"final"}:
        package.state = "final"
        package.completed_at = utcnow()
    elif task_states.issubset({"resident2_done", "final"}):
        package.state = "resident2_done"
    elif task_states.issubset({"resident_done", "resident2_done", "final"}):
        package.state = "resident_done"
    else:
        package.state = "pending"


def _int_form_value(name: str) -> int | None:
    try:
        return int(request.form.get(name) or "")
    except ValueError:
        return None
