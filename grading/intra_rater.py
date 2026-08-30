"""
Inline intra-rater grading routes surfaced within the dual grading flow.
TODO- features  dsipay and saving
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask import (
    session as flask_session,
)
from flask_login import current_user
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading_schemes.service import STANDARD_NON_GRADABLE_REASONS
from models import GradingsFeatures, ImageMetadata, IntraRaterGrade, IntraRaterTask
from project_annotations.service import (
    resolve_task_annotation_context,
    validate_geometry_policy,
)
from services.intra_rater_service import (
    STATE_PENDING,
    IntraRaterService,
    SubmitGradeParams,
    can_access_intra_rater_task,
)
from utils.dualGradingGetNextTasks import (
    get_next_eligible_arbitrator_task_atomic,
    get_next_eligible_resident2_task_atomic,
    get_next_eligible_resident_task_atomic,
)
from utils.feature_geometry import (
    parse_feature_geometry_payload,
    prepare_feature_geometry_for_storage,
    validate_feature_geometry_payload,
)
from utils.masterUtils import fetch_active_disease_gradings
from utils.utils2 import is_valid_uuid


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
    bp.add_url_rule(
        "/intra-task/<string:task_uuid>/feature-geometry",
        view_func=intra_rater_feature_geometry,
        methods=["GET"],
    )


@roles_required("ophthalmologist", "field_ophthalmologist")
def intra_rater_task(task_uuid: str):
    """Display a pending intra-rater reassessment."""
    resume_slot = (request.args.get("resume_slot") or "").strip().lower() or None
    resume_disease_id = request.args.get("resume_disease_id", type=int)

    if resume_slot not in {"resident", "resident2", "arbitrator"}:
        resume_slot = None
    task_uuid = (task_uuid or "").strip()
    if not task_uuid or not is_valid_uuid(task_uuid):
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

        if not can_access_intra_rater_task(db, actor=current_user, task=task):
            flash("You are not authorized to view this intra-rater task.", "danger")
            return redirect(url_for("grading.index"))

        if task.state != STATE_PENDING:
            flash("This intra-rater task is no longer available.", "info")
            return redirect(url_for("grading.index"))

        disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
        if not disease_gradings:
            flash("No disease gradings available for this intra-rater task.", "danger")
            return redirect(url_for("grading.index"))

        grading_guidelines = {grading.id: grading.guidelines for grading in disease_gradings}

        # Build grading features data for template
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

        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image_upload:
            image_uuid = task.direct_image_upload.uuid
        image_metadata = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == image_uuid,
                ImageMetadata.image_variant == "orig",
            )
            .first()
            if image_uuid
            else None
        )

        start_time_iso = datetime.now(timezone.utc).isoformat()
        start_time_key = f"intra_grading_start_time_{task_uuid}"
        flask_session[start_time_key] = start_time_iso

        effective_resume_disease_id = resume_disease_id or task.disease_id

        return render_template(
            "grading/intra_grading_task.html",
            task=task,
            disease_gradings=disease_gradings,
            grading_guidelines=grading_guidelines,
            grading_features=grading_features,
            image_uuid=image_uuid,
            image_metadata=image_metadata,
            resume_slot=resume_slot,
            resume_disease_id=effective_resume_disease_id,
            start_time_iso=start_time_iso,
            non_gradable_reasons=list(STANDARD_NON_GRADABLE_REASONS),
            annotation_context=resolve_task_annotation_context(db, task).to_dict(),
            current_user_id=getattr(current_user, "id", None),
        )


@roles_required("ophthalmologist", "field_ophthalmologist")
def intra_rater_feature_geometry(task_uuid: str):
    """Fetch stored feature geometry for an intra-rater task."""
    task_uuid = (task_uuid or "").strip()
    if not task_uuid or not is_valid_uuid(task_uuid):
        return jsonify({"success": False, "message": "Invalid intra-rater task reference."}), 400

    with transaction_scope() as db:
        task: Optional[IntraRaterTask] = (
            db.query(IntraRaterTask)
            .options(
                selectinload(IntraRaterTask.encounter_file),
                selectinload(IntraRaterTask.direct_image_upload),
            )
            .filter(IntraRaterTask.uuid == task_uuid)
            .first()
        )

        if task is None:
            return jsonify({"success": False, "message": "Intra-rater task not found."}), 404

        if not can_access_intra_rater_task(db, actor=current_user, task=task):
            return jsonify({"success": False, "message": "Not authorized to view geometry."}), 403

        existing_grade = (
            db.query(IntraRaterGrade)
            .filter(
                IntraRaterGrade.task_id == task.id,
                IntraRaterGrade.grader_user_id == current_user.id,
            )
            .first()
        )

        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image_upload:
            image_uuid = task.direct_image_upload.uuid
        image_metadata = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == image_uuid,
                ImageMetadata.image_variant == "orig",
            )
            .first()
            if image_uuid
            else None
        )

        geometry_payload = None
        if existing_grade and existing_grade.feature_geometry_json:
            geometry_payload = existing_grade.feature_geometry_json

        return jsonify(
            {
                "success": True,
                "task_uuid": task_uuid,
                "feature_geometry": geometry_payload,
                "image": {
                    "uuid": image_uuid,
                    "width": image_metadata.width if image_metadata else None,
                    "height": image_metadata.height if image_metadata else None,
                },
            }
        )


@roles_required("ophthalmologist", "field_ophthalmologist")
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
    
    # Get selected features from form
    raw_selected_features = request.form.getlist("selected_features")
    selected_feature_ids: list[int] = []
    for raw_feature in raw_selected_features:
        if raw_feature is None or raw_feature == "":
            continue
        try:
            selected_feature_ids.append(int(raw_feature))
        except (TypeError, ValueError):
            flash("Invalid feature selection submitted.", "danger")
            return redirect(_build_intra_task_url(task_uuid, resume_slot, resume_disease_id))

    # Deduplicate while preserving submission order
    unique_feature_ids: list[int] = []
    seen_feature_ids: set[int] = set()
    for feature_id in selected_feature_ids:
        if feature_id not in seen_feature_ids:
            unique_feature_ids.append(feature_id)
            seen_feature_ids.add(feature_id)

    selected_features_json: str | None = None
    raw_feature_geometry = request.form.get("feature_geometry_json")
    parsed_feature_geometry = None
    if raw_feature_geometry is not None:
        parsed_feature_geometry = parse_feature_geometry_payload(raw_feature_geometry)
        if raw_feature_geometry.strip() and parsed_feature_geometry is None:
            flash("Invalid feature geometry submitted.", "danger")
            return redirect(_build_intra_task_url(task_uuid, resume_slot, resume_disease_id))
    
    feature_metadata_by_id: dict[int, dict[str, object]] = {}
    # Validate selected features if any were provided
    if unique_feature_ids:
        with transaction_scope() as db:
            # Validate that features belong to the selected grading
            available_features = (
                db.query(GradingsFeatures)
                .filter(GradingsFeatures.disease_grading_id == label_id)
                .all()
            )
            features_by_id = {feature.id: feature for feature in available_features}
            invalid_features = [fid for fid in unique_feature_ids if fid not in features_by_id]
            if invalid_features:
                flash("One or more selected features are not valid for the chosen grade.", "danger")
                return redirect(_build_intra_task_url(task_uuid, resume_slot, resume_disease_id))

            selected_feature_entities = sorted(
                (features_by_id[fid] for fid in unique_feature_ids),
                key=lambda feature: ((feature.sr_no or 0), feature.id),
            )
            feature_metadata_by_id = {
                int(feature.id): {
                    "label": feature.label,
                    "sr_no": feature.sr_no,
                }
                for feature in selected_feature_entities
            }

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
    if resume_slot not in {"resident", "resident2", "arbitrator"}:
        resume_slot = None

    if not task_uuid or not is_valid_uuid(task_uuid):
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

        if not can_access_intra_rater_task(db, actor=current_user, task=task):
            flash("You are not authorized to submit this intra-rater task.", "danger")
            return redirect(url_for("grading.index"))

        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image_upload:
            image_uuid = task.direct_image_upload.uuid
        image_metadata = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == image_uuid,
                ImageMetadata.image_variant == "orig",
            )
            .first()
            if image_uuid
            else None
        )
        if raw_feature_geometry:
            is_valid_geometry, geometry_error = validate_feature_geometry_payload(
                parsed_feature_geometry, unique_feature_ids, image_metadata
            )
            if not is_valid_geometry:
                flash(geometry_error or "Invalid feature geometry submitted.", "danger")
                return redirect(_build_intra_task_url(task_uuid, resume_slot, resume_disease_id))
            annotation_context = resolve_task_annotation_context(db, task)
            is_policy_valid, policy_error = validate_geometry_policy(
                parsed_feature_geometry,
                annotation_context,
            )
            if not is_policy_valid:
                flash(policy_error or "Annotation policy validation failed.", "danger")
                return redirect(_build_intra_task_url(task_uuid, resume_slot, resume_disease_id))

        feature_geometry = (
            prepare_feature_geometry_for_storage(
                parsed_feature_geometry,
                image_metadata,
                feature_metadata_by_id=feature_metadata_by_id if unique_feature_ids else None,
                annotation_context=annotation_context.to_dict(),
            )
            if raw_feature_geometry and parsed_feature_geometry
            else None
        )

        if task.state != STATE_PENDING:
            flash("This intra-rater task has already been completed.", "info")
            return redirect(url_for("grading.index"))

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
            selected_features_json=selected_features_json,
            feature_geometry_json=feature_geometry,
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
        next_task_uuid = None
        try:
            with transaction_scope() as db:
                if resume_slot == "resident":
                    next_task = get_next_eligible_resident_task_atomic(
                        current_user.id,
                        actual_resume_disease_id,
                        db=db,
                    )
                elif resume_slot == "resident2":
                    next_task = get_next_eligible_resident2_task_atomic(
                        current_user.id,
                        actual_resume_disease_id,
                        db=db,
                    )
                else:
                    next_task = get_next_eligible_arbitrator_task_atomic(
                        current_user.id,
                        actual_resume_disease_id,
                        db=db,
                    )

                if isinstance(next_task, str):
                    flash(next_task, "info")
                    return redirect(url_for("grading.index"))

                if next_task is not None:
                    next_task_uuid = next_task.uuid
        except Exception:  # pragma: no cover - defensive logging via flash
            flash("Next task could not be loaded after intra-rater submission.", "warning")
            return redirect(url_for("grading.index"))

        if not next_task_uuid:
            flash("No more tasks available in the current grading queue.", "info")
            return redirect(url_for("grading.index"))

        return redirect(url_for("grading.dual_grading_task", task_uuid=next_task_uuid, slot_type=resume_slot))

    return redirect(url_for("grading.index"))
