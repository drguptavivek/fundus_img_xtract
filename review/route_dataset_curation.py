from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for, send_file
from flask_login import current_user
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from job_store import db_create_job
from models import (
    AIModel,
    CuratedDataset,
    CuratedDatasetItem,
    Disease,
    DiseaseGrading,
    EncounterFile,
    LabUnit,
    Session,
    DirectImageUpload,
    Job,
)
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from . import bp
from .discrepancy_export import (
    ExportTaskRow,
    enqueue_dataset_export,
    _fetch_filtered_rows,
    _fetch_rows_by_task_ids,
)
from .task_review import AI_REVIEW_STATUS_LABELS
from .discrepancy_export import EXPORT_DIR


def _build_filters_from_request(req) -> Dict[str, Any]:
    """Extract discrepancy-style filters from request args/form."""
    disease_id = req.get("disease_id", type=int)
    lab_unit_id = req.get("lab_unit_id", type=int)
    resident_grades = req.getlist("resident_grade")
    resident2_grades = req.getlist("resident2_grade")
    arbitrator_grades = req.getlist("arbitrator_grade")
    final_grades = req.getlist("final_grade")
    has_ai_grade = req.get("has_ai_grade", type=str)
    has_review = req.get("has_review", type=str)
    has_consensus = req.get("has_consensus", default="has_consensus", type=str)
    ai_model_ids = req.getlist("ai_model_id")
    ai_grades = req.getlist("ai_grade")
    ai_review_status = [
        status for status in req.getlist("ai_review_status") if status in AI_REVIEW_STATUS_LABELS
    ]

    if has_ai_grade != "yes":
        ai_model_ids = []
        ai_grades = []
        ai_review_status = []

    return {
        "disease_id": disease_id,
        "lab_unit_id": lab_unit_id,
        "resident_grade": resident_grades,
        "resident2_grade": resident2_grades,
        "arbitrator_grade": arbitrator_grades,
        "final_grade": final_grades,
        "has_ai_grade": has_ai_grade,
        "has_review": has_review,
        "has_consensus": has_consensus,
        "ai_model_id": ai_model_ids,
        "ai_grade": ai_grades,
        "ai_review_status": ai_review_status,
    }


def _filters_with_allowed(filters: Dict[str, Any], allowed_lab_units: Iterable[int]) -> Dict[str, Any]:
    """Apply allowed lab units to stored filters."""
    merged = dict(filters)
    merged["allowed_lab_units"] = list(allowed_lab_units)
    return merged


def _get_next_pending_row(filters: Dict[str, Any], decided_task_ids: Set[int]) -> Optional[ExportTaskRow]:
    """Return the next task row that is not yet decided for this dataset."""
    rows = _fetch_filtered_rows(filters)
    for row in rows:
        if row.task_id not in decided_task_ids:
            return row
    return None


def _fetch_options(db: Session, allowed_lab_units: Iterable[int]) -> Tuple[List[Disease], List[LabUnit], List[DiseaseGrading], List[AIModel]]:
    diseases = db.query(Disease).order_by(Disease.name).all()
    lab_units = (
        db.query(LabUnit)
        .filter(LabUnit.id.in_(list(allowed_lab_units)))
        .options(joinedload(LabUnit.hospital))
        .order_by(LabUnit.hospital_id, LabUnit.name)
        .all()
    )
    grade_options = db.query(DiseaseGrading).distinct(DiseaseGrading.impression).all()
    ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
    return diseases, lab_units, grade_options, ai_models


@bp.route("/dataset-curation", methods=["GET", "POST"])
@roles_required("admin", "data_manager")
def dataset_curation():
    """Create curated datasets using discrepancy-style filters."""
    db = Session()
    try:
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_units:
            flash("No lab units are available for dataset curation.", "error")
            return redirect(url_for("dashboard.dashboard_home"))

        diseases, lab_units, grade_options, ai_models = _fetch_options(db, allowed_lab_units)

        if request.method == "POST":
            filters = _build_filters_from_request(request.form)
            if not filters.get("disease_id"):
                flash("Disease selection is required to create a dataset.", "error")
                return redirect(url_for("review.dataset_curation", **request.args))

            dataset_name = (request.form.get("dataset_name") or "").strip()
            purpose = (request.form.get("dataset_purpose") or "").strip()
            auto_select_count = request.form.get("auto_select_count", type=int)
            if not dataset_name or not purpose:
                flash("Dataset name and purpose are required.", "error")
                return redirect(url_for("review.dataset_curation", **request.args))

            filters = _filters_with_allowed(filters, allowed_lab_units)
            dataset = CuratedDataset(
                name=dataset_name,
                purpose=purpose,
                filters_json=json.dumps(filters),
                disease_id=filters["disease_id"],
                created_by_user_id=current_user.id,
            )
            db.add(dataset)
            db.flush()

            selected_rows: List[ExportTaskRow] = []
            if auto_select_count and auto_select_count > 0:
                rows = _fetch_filtered_rows(filters)
                selected_rows = rows[:auto_select_count]
                for row in selected_rows:
                    db.add(
                        CuratedDatasetItem(
                            dataset_id=dataset.id,
                            task_id=row.task_id,
                            include_in_export=True,
                            selection_method="auto",
                            selected_by_user_id=current_user.id,
                        )
                    )
            db.commit()
            flash(
                f"Dataset created. Auto-selected {len(selected_rows)} tasks." if selected_rows else "Dataset created.",
                "success",
            )
            return redirect(url_for("review.dataset_detail", dataset_uuid=dataset.uuid))

        datasets = (
            db.query(CuratedDataset)
            .order_by(CuratedDataset.created_at.desc())
            .limit(20)
            .all()
        )
        dataset_stats: Dict[int, Dict[str, int]] = {}
        if datasets:
            dataset_ids = [d.id for d in datasets]
            rows = (
                db.query(
                    CuratedDatasetItem.dataset_id,
                    CuratedDatasetItem.include_in_export,
                    sa.func.count(CuratedDatasetItem.id),
                )
                .filter(CuratedDatasetItem.dataset_id.in_(dataset_ids))
                .group_by(CuratedDatasetItem.dataset_id, CuratedDatasetItem.include_in_export)
                .all()
            )
            for ds_id, include_flag, count in rows:
                ds_stats = dataset_stats.setdefault(ds_id, {"include": 0, "exclude": 0})
                if include_flag:
                    ds_stats["include"] += count
                else:
                    ds_stats["exclude"] += count

        return render_template(
            "review/dataset_curation.html",
            diseases=diseases,
            lab_units=lab_units,
            grade_options=grade_options,
            ai_models=ai_models,
            ai_review_status_labels=AI_REVIEW_STATUS_LABELS,
            datasets=datasets,
            dataset_stats=dataset_stats,
        )
    finally:
        db.close()


@bp.route("/dataset-curation/<dataset_uuid>", methods=["GET", "POST"])
@roles_required("admin", "data_manager")
def dataset_detail(dataset_uuid: str):
    """Manual screening page for a curated dataset."""
    db = Session()
    try:
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        dataset = db.query(CuratedDataset).filter(CuratedDataset.uuid == dataset_uuid).first()
        if not dataset:
            abort(404)

        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)):
            flash("You do not have access to the lab units for this dataset.", "error")
            return redirect(url_for("review.dataset_curation"))
        filters = _filters_with_allowed(stored_filters, allowed_lab_units)
        if not filters.get("allowed_lab_units"):
            flash("No permitted lab units available for this dataset.", "error")
            return redirect(url_for("review.dataset_curation"))
        if not filters.get("disease_id"):
            flash("Dataset is missing a disease filter; cannot proceed.", "error")
            return redirect(url_for("review.dataset_curation"))

        # Track decisions
        items = (
            db.query(CuratedDatasetItem)
            .filter(CuratedDatasetItem.dataset_id == dataset.id)
            .all()
        )
        decided_task_ids = {item.task_id for item in items}
        included_task_ids = [item.task_id for item in items if item.include_in_export]
        excluded_task_ids = [item.task_id for item in items if not item.include_in_export]

        # Evaluate total matches for the stored filters
        matching_rows = _fetch_filtered_rows(filters)
        total_matching = len(matching_rows)
        included_rows: List[ExportTaskRow] = _fetch_rows_by_task_ids(included_task_ids, dataset.disease_id) if included_task_ids else []
        excluded_rows: List[ExportTaskRow] = _fetch_rows_by_task_ids(excluded_task_ids, dataset.disease_id) if excluded_task_ids else []

        if request.method == "POST":
            task_id = request.form.get("task_id", type=int)
            decision = request.form.get("decision")
            if task_id and decision in ("include", "exclude"):
                include_flag = decision == "include"
                item = (
                    db.query(CuratedDatasetItem)
                    .filter(
                        CuratedDatasetItem.dataset_id == dataset.id,
                        CuratedDatasetItem.task_id == task_id,
                    )
                    .first()
                )
                if item:
                    item.include_in_export = include_flag
                    item.selection_method = "manual"
                    item.selected_by_user_id = current_user.id
                else:
                    db.add(
                        CuratedDatasetItem(
                            dataset_id=dataset.id,
                            task_id=task_id,
                            include_in_export=include_flag,
                            selection_method="manual",
                            selected_by_user_id=current_user.id,
                        )
                    )
                db.commit()
                decided_task_ids.add(task_id)
                flash("Decision saved.", "success")
                return redirect(url_for("review.dataset_detail", dataset_uuid=dataset_uuid))

        next_row = _get_next_pending_row(filters, decided_task_ids)
        next_image = None
        next_grades: Dict[str, Any] = {}
        next_meta: Dict[str, Any] = {}
        if next_row:
            if next_row.encounter_file_id:
                next_image = db.get(EncounterFile, next_row.encounter_file_id)
            elif next_row.direct_image_upload_id:
                next_image = db.get(DirectImageUpload, next_row.direct_image_upload_id)
            try:
                details = json.loads(next_row.grading_details_json or "[]")
                for item in details:
                    role = item.get("role_slot")
                    if not role:
                        continue
                    next_grades[role] = {
                        "impression": item.get("grade_name"),
                        "comment": item.get("comment"),
                        "ai_model_name": item.get("ai_model_name"),
                        "ai_model_version": item.get("ai_model_version"),
                        "ai_probability": item.get("ai_probability"),
                    }
                if next_row.ai_review_statuses or next_row.ai_review_comments:
                    ai_block = next_grades.setdefault("ai", {})
                    ai_block["ai_review_statuses"] = next_row.ai_review_statuses
                    ai_block["ai_review_comments"] = next_row.ai_review_comments
            except Exception:
                next_grades = {}
            next_meta = {
                "lab_unit": next_row.lab_unit,
                "hospital": next_row.hospital,
            }

        include_count = sum(1 for i in items if i.include_in_export)
        exclude_count = sum(1 for i in items if not i.include_in_export)

        return render_template(
            "review/dataset_detail.html",
            dataset=dataset,
            include_count=include_count,
            exclude_count=exclude_count,
            next_row=next_row,
            next_image=next_image,
            next_grades=next_grades,
            next_meta=next_meta,
            ai_review_status_labels=AI_REVIEW_STATUS_LABELS,
            total_matching=total_matching,
            filters_display=filters,
            included_rows=included_rows,
            excluded_rows=excluded_rows,
        )
    finally:
        db.close()


@bp.route("/dataset-export/<dataset_uuid>", methods=["POST"])
@roles_required("admin", "data_manager")
def dataset_export(dataset_uuid: str):
    """Queue export for a curated dataset."""
    db = Session()
    try:
        dataset = db.query(CuratedDataset).filter(CuratedDataset.uuid == dataset_uuid).first()
        if not dataset:
            abort(404)

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_units:
            flash("You are not allowed to export datasets.", "error")
            return redirect(url_for("review.dataset_curation"))
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)):
            flash("You do not have access to the lab units for this dataset.", "error")
            return redirect(url_for("review.dataset_curation"))

        items = (
            db.query(CuratedDatasetItem)
            .filter(
                CuratedDatasetItem.dataset_id == dataset.id,
                CuratedDatasetItem.include_in_export.is_(True),
            )
            .all()
        )
        task_ids = [item.task_id for item in items]
        if not task_ids:
            flash("No tasks selected for export in this dataset.", "error")
            return redirect(url_for("review.dataset_detail", dataset_uuid=dataset_uuid))

        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        ip = xff or (request.remote_addr or "-")
        uploader_username = getattr(current_user, "username", None)
        uploader_user_id = getattr(current_user, "id", None)
        job_token = db_create_job(
            ["dataset_export"],
            [],
            uploader_user_id=uploader_user_id,
            uploader_username=uploader_username,
            uploader_ip=ip,
            upload_type="dataset_export",
        )

        metadata = {
            "dataset_name": dataset.name,
            "dataset_purpose": dataset.purpose,
            "disease_id": dataset.disease_id,
            **stored_filters,
        }
        from flask import current_app

        enqueue_dataset_export(current_app._get_current_object(), job_token, dataset.id, task_ids, metadata)
        flash("Dataset export queued.", "info")
        return redirect(url_for("jobs.job_status_page", job_token=job_token))
    finally:
        db.close()


@bp.route("/dataset-export/<job_token>/<path:filename>", methods=["GET"])
@roles_required("admin", "data_manager")
def dataset_export_download(job_token: str, filename: str):
    """Serve dataset export artifacts."""
    with Session() as db:
        job = db.query(Job).filter(Job.token == job_token, Job.upload_type == "dataset_export").first()
        if not job:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if job.lab_unit_id is None and job.uploader_user_id != current_user.id:
            abort(404)
        if job.lab_unit_id and job.lab_unit_id not in allowed_lab_units and job.uploader_user_id != current_user.id:
            abort(404)

        export_path = (EXPORT_DIR / job_token / filename).resolve()
        if not export_path.exists() or EXPORT_DIR not in export_path.parents:
            abort(404)
        return send_file(export_path, as_attachment=True)
