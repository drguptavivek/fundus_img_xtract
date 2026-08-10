"""Package-based EncounterSet grading views."""
from __future__ import annotations

import logging

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from markupsafe import Markup
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from encounter_sets.grading_records import (
    EncounterSetGradingError,
    EncounterSetSubmissionInputDTO,
    StaleEncounterSetPackageError,
    TargetGradeInputDTO,
    editable_tasks,
    submit_package,
)
from grading.grade_feature_submission import (
    GradeFeatureValidationError,
    parse_selected_features,
    prepare_grade_feature_submission,
    serialize_grade_features,
)
from grading_schemes.service import STANDARD_NON_GRADABLE_REASONS, sanitize_guidelines_html
from models import DiseaseGrading, EncounterSetGradingPackage, EncounterSetGradingScope, Grade, GradingTask
from utils.dualGradingEligibility import get_user_eligibility_for_task
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
@roles_required("resident", "ophthalmologist")
def encounter_set_package_grading(package_uuid: str, slot_type: str):
    if slot_type not in {"resident", "resident2", "arbitrator"}:
        flash("Invalid grading slot.", "danger")
        return redirect(url_for("grading.index"))

    with transaction_scope() as db:
        package = _fetch_package(db, package_uuid)
        if not package:
            flash("EncounterSet grading package not found.", "danger")
            return redirect(url_for("grading.index"))

        editable = editable_tasks(package, slot_type, current_user.id)
        tasks = (
            _ordered_tasks(editable)
            if slot_type == "arbitrator"
            else _ordered_package_tasks(package)
        )
        slot_eligible = _package_slot_eligible(db, package, editable, slot_type)
        editable_ids = {task.id for task in editable}
        task_panels = [
            _task_panel(
                db,
                task,
                slot_type,
                package=package,
                available=slot_eligible and task.id in editable_ids,
            )
            for task in tasks
        ]
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
@roles_required("resident", "ophthalmologist")
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

        expected_revision = _int_form_value("package_revision")
        if expected_revision is None:
            flash("The package revision is missing. Reload before submitting.", "danger")
            return redirect(url_for("grading.encounter_set_package_grading", package_uuid=package_uuid, slot_type=slot_type))
        editable = editable_tasks(package, slot_type, current_user.id)
        if not _package_slot_eligible(db, package, editable, slot_type):
            flash("This package slot is not allocated to you.", "danger")
            return redirect(url_for("grading.index"))

        submissions = []
        for task in editable:

            label_id = _int_form_value(f"label_id_{task.uuid}")
            if not label_id:
                flash("Please select a grade for every available package target.", "warning")
                return redirect(url_for("grading.encounter_set_package_grading", package_uuid=package_uuid, slot_type=slot_type))

            label = (
                db.query(DiseaseGrading)
                .filter(
                    DiseaseGrading.id == label_id,
                    DiseaseGrading.disease_id == task.disease_id,
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

            submissions.append(TargetGradeInputDTO(
                task_uuid=task.uuid,
                disease_grading_id=label_id,
                comment=comment,
                selected_features_json=feature_submission.selected_features_json,
                feature_geometry_json=feature_submission.feature_geometry_json,
            ))

        if not submissions:
            flash("No package targets were updated.", "warning")
            return redirect(
                url_for(
                    "grading.encounter_set_package_grading",
                    package_uuid=package_uuid,
                    slot_type=slot_type,
                )
            )

        try:
            submit_package(db, package, EncounterSetSubmissionInputDTO(
                package_uuid=package.uuid,
                role_slot=slot_type,
                grader_user_id=current_user.id,
                expected_package_revision=expected_revision,
                targets=tuple(submissions),
            ))
        except StaleEncounterSetPackageError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("grading.encounter_set_package_grading", package_uuid=package_uuid, slot_type=slot_type))
        except EncounterSetGradingError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("grading.encounter_set_package_grading", package_uuid=package_uuid, slot_type=slot_type))

        for task in editable:
            cleanup_task_tracker(task.id, current_user.id, slot_type, db)

        flash(f"Submitted {len(submissions)} target grade(s) for {package.name}.", "success")
        return redirect(url_for("grading.index"))


def _fetch_package(db, package_uuid: str, *, for_update: bool = False) -> EncounterSetGradingPackage | None:
    query = (
        db.query(EncounterSetGradingPackage)
        .options(
            selectinload(EncounterSetGradingPackage.patient_encounter),
            selectinload(EncounterSetGradingPackage.submissions),
            selectinload(EncounterSetGradingPackage.scopes)
            .selectinload(EncounterSetGradingScope.tasks),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.disease),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.encounter_set_image),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.grades).selectinload(Grade.label),
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.consensus),
        )
        .filter(EncounterSetGradingPackage.uuid == package_uuid)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def _ordered_package_tasks(package: EncounterSetGradingPackage) -> list[GradingTask]:
    return _ordered_tasks(
        [task for task in package.tasks if task.state != "final" or task.grades]
    )


def _ordered_tasks(tasks: list[GradingTask]) -> list[GradingTask]:
    return sorted(
        tasks,
        key=lambda task: (
            (
                task.encounter_set_scope.display_order
                if getattr(task, "encounter_set_scope", None)
                else 0
            ),
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


def _task_panel(
    db,
    task: GradingTask,
    slot_type: str,
    *,
    package=None,
    available: bool | None = None,
) -> dict:
    label_ids = {
        row.get("id")
        for row in (
            ((package.policy_snapshot_json if package else {}) or {})
            .get("grading_definitions", {})
            .get(str(task.disease_id), {})
            .get("labels", [])
        )
    }
    label_query = (
        db.query(DiseaseGrading)
        .options(selectinload(DiseaseGrading.features))
    )
    if package is not None:
        label_query = label_query.filter(
            DiseaseGrading.disease_id == task.disease_id,
            DiseaseGrading.id.in_(label_ids),
        )
    else:
        label_query = label_query.filter(
            DiseaseGrading.disease_id == task.disease_id,
            DiseaseGrading.is_active.is_(True),
        )
    labels = label_query.order_by(DiseaseGrading.display_order).all()
    existing = next(
        (
            grade for grade in task.grades
            if grade.grader_user_id == current_user.id and grade.role_slot == slot_type
        ),
        None,
    )
    eligibility_checked = available is None
    if eligibility_checked:
        available = get_user_eligibility_for_task(
            db, current_user.id, task.id, slot_type
        )
    if not available:
        unavailable_reason = (
            "Not allocated to you"
            if eligibility_checked
            else "Not available at this grading stage"
        )
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
        "available": available,
        "unavailable_reason": unavailable_reason,
    }


def _package_slot_eligible(db, package, tasks, slot_type: str) -> bool:
    owner_id = getattr(package, f"{slot_type}_user_id")
    if owner_id is not None:
        return owner_id == current_user.id
    return any(
        get_user_eligibility_for_task(db, current_user.id, task.id, slot_type)
        for task in tasks
    )


def _int_form_value(name: str) -> int | None:
    try:
        return int(request.form.get(name) or "")
    except ValueError:
        return None
