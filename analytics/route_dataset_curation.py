from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import sqlalchemy as sa
from flask import abort, flash, redirect, render_template, request, url_for, send_file, current_app
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
from db_transaction_manager import get_db_session
from utils.hospital_scoping import apply_scoping
from . import bp
from review.discrepancy_export import (
    ExportTaskRow,
    enqueue_dataset_export,
    _fetch_filtered_rows,
    _fetch_rows_by_task_ids,
)
from review.task_review import AI_REVIEW_STATUS_LABELS
from review.task_review import AI_REVIEW_STATUS_LABELS
from review.discrepancy_export import EXPORT_DIR
from utils.filename_utils import sanitize_export_filename
from werkzeug.utils import secure_filename


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

    # Random selection parameters
    randomize_selection = req.get("randomize_selection", type=str)
    random_seed = req.get("random_seed", type=str)

    # Dataset exclusivity: exclude tasks from selected existing datasets
    excluded_dataset_ids_raw = req.getlist("excluded_dataset_ids")
    excluded_dataset_ids = []
    for ds_id in excluded_dataset_ids_raw:
        try:
            excluded_dataset_ids.append(int(ds_id))
        except (ValueError, TypeError):
            # Skip invalid dataset IDs
            pass

    if has_ai_grade != "yes":
        ai_model_ids = []
        ai_grades = []
        ai_review_status = []

    # Process randomize flag: "yes" or "on" = True, others = False
    randomize_bool = randomize_selection in ("yes", "on", "true", "1")

    # Process seed: convert to int if provided
    seed_value = None
    if random_seed:
        try:
            seed_value = int(random_seed)
        except ValueError:
            # If seed is not a valid integer, hash the string to get an int
            import hashlib
            seed_value = int(hashlib.sha256(random_seed.encode()).hexdigest(), 16) % (2 ** 31)

    return {
        "disease_id": disease_id,
        "lab_unit_id": lab_unit_id,
        "resident_grade": resident_grades,
        "resident2_grade": resident2_grades,
        "arbitrator_grade": arbitrator_grades,
        "final_grade": final_grades,
        "require_final_grade": True,
        "has_ai_grade": has_ai_grade,
        "has_review": has_review,
        "has_consensus": has_consensus,
        "ai_model_id": ai_model_ids,
        "ai_grade": ai_grades,
        "ai_review_status": ai_review_status,
        "randomize_selection": randomize_bool,
        "random_seed": seed_value,
        "excluded_dataset_ids": excluded_dataset_ids,
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


def _fetch_options(db: Session, user: Any) -> Tuple[List[Disease], List[LabUnit], List[DiseaseGrading], List[AIModel]]:
    diseases = db.query(Disease).order_by(Disease.name).all()
    
    lab_units_query = db.query(LabUnit)
    # Apply hospital scoping for dataset creation options
    lab_units_query = apply_scoping(lab_units_query, LabUnit, user, 'dataset_creation')
    
    lab_units = (
        lab_units_query
        .options(joinedload(LabUnit.hospital))
        .order_by(LabUnit.hospital_id, LabUnit.name)
        .all()
    )
    grade_options = db.query(DiseaseGrading).distinct(DiseaseGrading.impression).all()
    ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
    return diseases, lab_units, grade_options, ai_models


def _ai_summary(row: ExportTaskRow) -> str:
    """Return concise AI info: grade, probability, model, review statuses/comments."""
    grade = None
    prob = None
    model = None
    try:
        details = json.loads(row.grading_details_json or "[]")
        for item in details:
            if item.get("role_slot") == "ai":
                grade = item.get("grade_name") or item.get("impression")
                prob = item.get("ai_probability") or item.get("ai_prob") or item.get("probability")
                model = item.get("ai_model_name")
                break
    except Exception:
        pass

    if not prob and row.ai_review_comments:
        prob_re = re.compile(r"(?:ai\s*prob(?:ability)?|prob(?:ability)?)[:=]?\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
        for comment in row.ai_review_comments:
            m = prob_re.search(comment or "")
            if m:
                prob = m.group(1)
                break

    statuses = row.ai_review_statuses or []
    comments = row.ai_review_comments or []
    parts: list[str] = []
    if grade:
        parts.append(grade)
    if prob:
        parts.append(f"p={prob}")
    if model:
        parts.append(model)
    if statuses:
        parts.append("review: " + ", ".join(statuses))
    if comments:
        parts.append("comment: " + "; ".join(comments))
    return " ; ".join(parts) if parts else "—"


@bp.route("/dataset-curation", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_curation():
    """Create curated datasets using discrepancy-style filters."""
    with get_db_session() as db:
        diseases, lab_units, grade_options, ai_models = _fetch_options(db, current_user)
        allowed_lab_units = [lu.id for lu in lab_units]
        
        if not allowed_lab_units and not current_user.is_master_admin:
            flash("No lab units are available for dataset curation.", "error")
            return redirect(url_for("dashboard.hospital_dashboard"))

        if request.method == "POST":
            filters = _build_filters_from_request(request.form)
            if not filters.get("disease_id"):
                flash("Disease selection is required to create a dataset.", "error")
                return redirect(url_for("analytics.dataset_curation", **request.args))

            dataset_name = (request.form.get("dataset_name") or "").strip()
            purpose = (request.form.get("dataset_purpose") or "").strip()
            auto_select_count = request.form.get("auto_select_count", type=int)
            if not dataset_name or not purpose:
                flash("Dataset name and purpose are required.", "error")
                return redirect(url_for("analytics.dataset_curation", **request.args))

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
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset.uuid))

        datasets_query = db.query(CuratedDataset).filter(CuratedDataset.is_active.is_(True))
        # Apply hospital scoping to datasets listing (admins see all in hospital, creators see all assigned)
        # CuratedDataset doesn't have hospital_id/lab_unit_id, but it has created_by_user_id.
        # However, for now we let it be filtered by disease_id or just show recent if they have role.
        
        datasets = (
            datasets_query
            .order_by(CuratedDataset.created_at.desc())
            .limit(20)
            .all()
        )
        dataset_stats: Dict[int, Dict[str, int]] = {}
        dataset_jobs: Dict[str, Dict[str, str]] = {}
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

            # Find latest dataset_export job per dataset (within retention window)
            retention_hours = getattr(current_app.config, "EXPORT_RETENTION_HOURS", 24)
            cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
            job_rows = (
                db.query(Job)
                .filter(Job.upload_type == "dataset_export")
                .filter(Job.created_at >= cutoff_dt)
                .order_by(Job.created_at.desc())
                .all()
            )
            for job in job_rows:
                try:
                    payload = job.payload or {}
                    meta = payload.get("metadata") or {}
                    ds_uuid = meta.get("dataset_uuid") or meta.get("dataset_id")
                    if ds_uuid:
                        dataset_jobs[str(ds_uuid)] = {
                            "job_token": job.token,
                            "created_at": job.created_at,
                        }
                except Exception:
                    continue

        return render_template(
            "review/dataset_curation.html",
            diseases=diseases,
            lab_units=lab_units,
            grade_options=grade_options,
            ai_models=ai_models,
            ai_review_status_labels=AI_REVIEW_STATUS_LABELS,
            datasets=datasets,
            dataset_stats=dataset_stats,
            dataset_jobs=dataset_jobs,
        )



@bp.route("/dataset-curation/<dataset_uuid>", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_detail(dataset_uuid: str):
    """Manual screening page for a curated dataset."""
    with get_db_session() as db:
        # Get allowed lab units via scoped query
        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, 'dataset_creation')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)

        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)):
            flash("You do not have access to the lab units for this dataset.", "error")
            return redirect(url_for("analytics.dataset_curation"))
        filters = _filters_with_allowed(stored_filters, allowed_lab_units)
        if not filters.get("allowed_lab_units"):
            flash("No permitted lab units available for this dataset.", "error")
            return redirect(url_for("analytics.dataset_curation"))
        if not filters.get("disease_id"):
            flash("Dataset is missing a disease filter; cannot proceed.", "error")
            return redirect(url_for("analytics.dataset_curation"))

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
        included_display = [
            {
                "task_id": r.task_id,
                "final_impression": r.final_impression,
                "lab_unit": r.lab_unit,
                "ai_summary": _ai_summary(r),
            }
            for r in included_rows
        ]
        excluded_display = [
            {
                "task_id": r.task_id,
                "final_impression": r.final_impression,
                "lab_unit": r.lab_unit,
                "ai_summary": _ai_summary(r),
            }
            for r in excluded_rows
        ]

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
                return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

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
            included_rows=included_display,
            excluded_rows=excluded_display,
        )



@bp.route("/dataset-export/<dataset_uuid>", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator")
def dataset_export(dataset_uuid: str):
    """Queue export for a curated dataset."""
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)

        # Get allowed lab units via scoped query
        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, 'dataset_creation')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        
        if not allowed_lab_units and not current_user.is_master_admin:
            flash("You are not allowed to export datasets.", "error")
            return redirect(url_for("analytics.dataset_curation"))
            
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if not current_user.has_role('dataset_creator') and not current_user.is_master_admin:
            if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)):
                flash("You do not have access to the lab units for this dataset.", "error")
                return redirect(url_for("analytics.dataset_curation"))

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
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

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



@bp.route("/dataset-export/<job_token>/<path:filename>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator")
def dataset_export_download(job_token: str, filename: str):
    """Serve dataset export artifacts."""
    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_token, Job.upload_type == "dataset_export").first()
        if not job:
            abort(404)
        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, 'dataset_creation')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        
        if job.lab_unit_id is None and job.uploader_user_id != current_user.id and not current_user.is_master_admin:
            abort(404)
        if job.lab_unit_id and job.lab_unit_id not in allowed_lab_units and job.uploader_user_id != current_user.id:
            abort(404)

        # Validate filename safety
        if filename != secure_filename(filename):
            abort(404)
        
        # Ensure filename looks like an export (basic check)
        if ".." in filename or "/" in filename or "\\" in filename:
             abort(404)

        export_path = (EXPORT_DIR / job_token / filename).resolve()
        if not export_path.exists() or EXPORT_DIR not in export_path.parents:
            abort(404)
        return send_file(export_path, as_attachment=True)


@bp.route("/dataset-curation/<dataset_uuid>/delete", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "dataset_creator")
def dataset_delete(dataset_uuid: str):
    """Delete a curated dataset and release its tasks."""
    import logging
    from utils.log_sanitize import sanitize_log_value
    logger = logging.getLogger("analytics")

    with get_db_session() as db:
        dataset = db.query(CuratedDataset).filter(CuratedDataset.uuid == dataset_uuid).first()

        if not dataset:
            abort(404)

        # Access control: user must have access to the dataset's lab units
        lab_units_query = apply_scoping(db.query(LabUnit), LabUnit, current_user, 'dataset_creation')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]

        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])

        if not current_user.is_master_admin:
            if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)):
                flash("You do not have permission to delete this dataset.", "error")
                return redirect(url_for("analytics.dataset_curation"))

        # Count included items for user feedback
        include_count = db.query(CuratedDatasetItem).filter_by(
            dataset_id=dataset.id,
            include_in_export=True
        ).count()

        # Log deletion for audit
        logger.info(
            "Dataset deleted: %s (id=%s, uuid=%s, include_count=%s) by user %s",
            sanitize_log_value(dataset.name),
            dataset.id,
            dataset.uuid,
            include_count,
            sanitize_log_value(current_user.username),
        )

        # Cascade delete handles CuratedDatasetItem cleanup automatically
        db.delete(dataset)
        db.commit()

        flash(
            f"Dataset '{dataset.name}' deleted. {include_count} tasks are now available for selection.",
            "success"
        )
        return redirect(url_for("analytics.dataset_curation"))
