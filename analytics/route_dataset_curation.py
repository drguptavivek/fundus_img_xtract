from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import sqlalchemy as sa
import random
from flask import abort, flash, redirect, render_template, request, session, url_for, send_file, current_app, make_response
from flask_login import current_user
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from auth.security import validate_email
from auth.utils import utcnow
from app_cache import cache
from job_store import db_create_job
from models import (
    AIModel,
    CuratedDataset,
    CuratedDatasetItem,
    DatasetExport,
    DatasetShare,
    Disease,
    DiseaseGrading,
    EncounterFile,
    LabUnit,
    Session,
    DirectImageUpload,
    GradingTask,
    ImageMetadata,
    ImagePiiVerification,
    User,
    Job,
)
from db_transaction_manager import get_db_session
from utils.final_grade_basis import final_grade_basis_label, normalize_final_grade_basis
from authz import scope
from utils.dataset_share import generate_share_otp, generate_share_token, hash_share_otp, hash_share_token
from utils.emails import build_dataset_share_email_html, build_inline_logo_image, send_email
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
    final_grade_basis = normalize_final_grade_basis(req.get("final_grade_basis", type=str))
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
        "final_grade_basis": final_grade_basis,
        "ai_model_id": ai_model_ids,
        "ai_grade": ai_grades,
        "ai_review_status": ai_review_status,
        "randomize_selection": randomize_bool,
        "random_seed": seed_value,
        "excluded_dataset_ids": excluded_dataset_ids,
    }


def _filters_with_allowed(filters: Dict[str, Any], allowed_lab_units: Iterable[int]) -> Dict[str, Any]:
    """Apply the curation scope: classical for unowned rows, project-wide for owned ones.

    A row with no project follows the established lab-unit rule. A row owned
    by a project is curatable only by a project ``dataset_creator`` holding a
    project-wide grant, so authority over one lab of a project does not
    extend to the project's data as a whole.

    This mirrors the ``dataset.curation.*`` policies in ``authz.policies``;
    the curation screen reads a materialized view through raw SQL, so the
    same rule is expressed here rather than through the ORM predicate.
    """
    merged = dict(filters)
    merged["allowed_lab_units"] = list(allowed_lab_units)
    is_admin = current_user.has_role("admin") or current_user.is_master_admin
    # Legacy per-lab capability rows never conferred curation at project
    # scope; the project role grant is now the only route in.
    merged["project_capability_columns"] = []
    merged["project_capability_role_names"] = [] if is_admin else ["dataset_creator"]
    merged["project_capability_require_project_scope"] = True
    merged["allow_classical_capability"] = True
    merged["project_capability_user_id"] = current_user.id
    merged["final_grade_basis"] = normalize_final_grade_basis(merged.get("final_grade_basis"))
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
    lab_units_query = scope(db, lab_units_query, LabUnit, user, 'dataset.curation.view')
    
    lab_units = (
        lab_units_query
        .options(joinedload(LabUnit.hospital))
        .order_by(LabUnit.hospital_id, LabUnit.name)
        .all()
    )
    grade_options = db.query(DiseaseGrading).distinct(DiseaseGrading.impression).all()
    ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
    return diseases, lab_units, grade_options, ai_models


def _build_screen_rows(
    items: Sequence[CuratedDatasetItem],
    disease_id: int,
    final_grade_basis: str,
    sort_by: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    if sort_by == "added_desc":
        ordered_items = sorted(items, key=lambda item: item.selected_at or utcnow(), reverse=True)
    elif sort_by == "added_asc":
        ordered_items = sorted(items, key=lambda item: item.selected_at or utcnow())
    else:
        ordered_items = sorted(items, key=lambda item: item.task_id)
    task_ids = [item.task_id for item in ordered_items]
    if not task_ids:
        return [], [], []

    rows = _fetch_rows_by_task_ids(task_ids, disease_id, final_grade_basis)
    row_by_id = {row.task_id: row for row in rows}
    include_map = {item.task_id: item.include_in_export for item in items}
    selected_map = {item.task_id: item.selected_at for item in items}
    method_map = {item.task_id: item.selection_method for item in items}

    screen_rows: list[dict] = []
    for idx, task_id in enumerate(task_ids, start=1):
        row = row_by_id.get(task_id)
        if not row:
            continue
        image_uuid = row.encounter_file_uuid or row.direct_image_uuid or row.image_uuid
        if not image_uuid:
            continue
        image_kind = "encounter" if row.encounter_file_uuid else "direct"
        screen_rows.append(
            {
                "task_id": row.task_id,
                "image_uuid": image_uuid,
                "image_kind": image_kind,
                "final_impression": row.final_impression,
                "lab_unit": row.lab_unit,
                "ai_summary": _ai_summary(row),
                "is_excluded": not include_map.get(task_id, True),
                "index": idx,
                "selected_at": selected_map.get(task_id),
                "selection_method": method_map.get(task_id),
            }
        )

    included_display = [row for row in screen_rows if not row["is_excluded"]]
    excluded_display = [row for row in screen_rows if row["is_excluded"]]
    return screen_rows, included_display, excluded_display


def _build_screen_page_rows(
    db: Session,
    items: Sequence[Any],
    disease_id: int,
    final_grade_basis: str,
    offset: int,
) -> list[dict]:
    """Return paginated screen rows for the current page."""
    task_ids = [item.task_id for item in items]
    if not task_ids:
        return []

    rows = _fetch_rows_by_task_ids(task_ids, disease_id, final_grade_basis)
    row_by_id = {row.task_id: row for row in rows}
    include_map = {item.task_id: item.include_in_export for item in items}
    selected_map = {item.task_id: item.selected_at for item in items}
    method_map = {item.task_id: item.selection_method for item in items}
    edited_map = {item.task_id: getattr(item, "edited_filename", None) for item in items}

    image_keys: list[tuple[str, str]] = []
    for row in rows:
        image_uuid = row.encounter_file_uuid or row.direct_image_uuid or row.image_uuid
        if not image_uuid:
            continue
        if row.encounter_file_uuid:
            variant = "orig"
        else:
            variant = "edited" if edited_map.get(row.task_id) else "orig"
        image_keys.append((image_uuid, variant))

    metadata_map: dict[tuple[str, str], ImageMetadata] = {}
    if image_keys:
        uuids = list({uuid for uuid, _ in image_keys})
        for meta in (
            db.query(ImageMetadata)
            .filter(ImageMetadata.image_uuid.in_(uuids))
            .all()
        ):
            metadata_map[(meta.image_uuid, meta.image_variant)] = meta

    screen_rows: list[dict] = []
    for idx, task_id in enumerate(task_ids, start=offset + 1):
        row = row_by_id.get(task_id)
        if not row:
            continue
        image_uuid = row.encounter_file_uuid or row.direct_image_uuid or row.image_uuid
        if not image_uuid:
            continue
        image_kind = "encounter" if row.encounter_file_uuid else "direct"
        variant = "orig" if row.encounter_file_uuid else ("edited" if edited_map.get(task_id) else "orig")
        meta = metadata_map.get((image_uuid, variant))
        metadata_payload = None
        if meta:
            metadata_payload = {
                "width": meta.width,
                "height": meta.height,
                "format": meta.format,
                "mode": meta.mode,
                "is_grayscale": meta.is_grayscale,
                "has_alpha": meta.has_alpha,
                "dpi_x": meta.dpi_x,
                "dpi_y": meta.dpi_y,
                "avg_luminance": meta.avg_luminance,
                "max_luminance": meta.max_luminance,
                "luminance_std": meta.luminance_std,
                "mean_r": meta.mean_r,
                "mean_g": meta.mean_g,
                "mean_b": meta.mean_b,
                "median_r": meta.median_r,
                "median_g": meta.median_g,
                "median_b": meta.median_b,
                "file_size_bytes": meta.file_size_bytes,
                "exif_present": bool(meta.exif_json),
                "iptc_present": bool(meta.iptc_json),
                "size_ok": bool(meta.width and meta.height and meta.width >= 1024 and meta.height >= 768),
            }
        screen_rows.append(
            {
                "task_id": row.task_id,
                "image_uuid": image_uuid,
                "image_kind": image_kind,
                "image_variant": variant,
                "final_impression": row.final_impression,
                "lab_unit": row.lab_unit,
                "ai_summary": _ai_summary(row),
                "metadata": metadata_payload,
                "is_excluded": not include_map.get(task_id, True),
                "index": idx,
                "selected_at": selected_map.get(task_id),
                "selection_method": method_map.get(task_id),
            }
        )
    return screen_rows


_SCREEN_CACHE_TIMEOUT = 10 * 60  # 10 minutes


def _apply_pii_filter(query, pii_filter: str):
    if pii_filter != "detected":
        return query
    variant_case = sa.case(
        (DirectImageUpload.edited_filename.isnot(None), "edited"),
        else_="orig",
    )
    join_clause = sa.or_(
        sa.and_(
            EncounterFile.uuid.isnot(None),
            ImagePiiVerification.image_uuid == EncounterFile.uuid,
            ImagePiiVerification.image_variant == "orig",
        ),
        sa.and_(
            DirectImageUpload.uuid.isnot(None),
            ImagePiiVerification.image_uuid == DirectImageUpload.uuid,
            ImagePiiVerification.image_variant == variant_case,
        ),
    )
    return query.join(ImagePiiVerification, join_clause).filter(ImagePiiVerification.pii_status == "detected")


def _apply_color_filter(query, color_filter: str):
    if color_filter == "all":
        return query
    variant_case = sa.case(
        (DirectImageUpload.edited_filename.isnot(None), "edited"),
        else_="orig",
    )
    join_clause = sa.or_(
        sa.and_(
            EncounterFile.uuid.isnot(None),
            ImageMetadata.image_uuid == EncounterFile.uuid,
            ImageMetadata.image_variant == "orig",
        ),
        sa.and_(
            DirectImageUpload.uuid.isnot(None),
            ImageMetadata.image_uuid == DirectImageUpload.uuid,
            ImageMetadata.image_variant == variant_case,
        ),
    )
    query = query.join(ImageMetadata, join_clause)
    if color_filter == "grayscale":
        return query.filter(ImageMetadata.is_grayscale.is_(True))
    if color_filter == "color":
        return query.filter(ImageMetadata.is_grayscale.is_(False))
    return query


def _count_dataset_items(db: Session, dataset_id: int, pii_filter: str, color_filter: str) -> int:
    base_query = (
        db.query(sa.func.count(sa.distinct(CuratedDatasetItem.id)))
        .join(GradingTask, GradingTask.id == CuratedDatasetItem.task_id)
        .outerjoin(EncounterFile, GradingTask.encounter_file_id == EncounterFile.id)
        .outerjoin(DirectImageUpload, GradingTask.direct_image_upload_id == DirectImageUpload.id)
        .filter(CuratedDatasetItem.dataset_id == dataset_id)
    )
    base_query = _apply_pii_filter(base_query, pii_filter)
    base_query = _apply_color_filter(base_query, color_filter)
    total = base_query.scalar()
    return int(total or 0)


def _count_dataset_items_by_export_state(
    db: Session,
    dataset_id: int,
    pii_filter: str,
    color_filter: str,
    include_in_export: bool,
) -> int:
    """Return count of dataset items for one export state under the active screen filter."""
    base_query = (
        db.query(sa.func.count(sa.distinct(CuratedDatasetItem.id)))
        .join(GradingTask, GradingTask.id == CuratedDatasetItem.task_id)
        .outerjoin(EncounterFile, GradingTask.encounter_file_id == EncounterFile.id)
        .outerjoin(DirectImageUpload, GradingTask.direct_image_upload_id == DirectImageUpload.id)
        .filter(
            CuratedDatasetItem.dataset_id == dataset_id,
            CuratedDatasetItem.include_in_export.is_(include_in_export),
        )
    )
    base_query = _apply_pii_filter(base_query, pii_filter)
    base_query = _apply_color_filter(base_query, color_filter)
    total = base_query.scalar()
    return int(total or 0)


@cache.memoize(timeout=_SCREEN_CACHE_TIMEOUT)
def _get_dataset_screen_page_cached(
    dataset_id: int,
    disease_id: int,
    final_grade_basis: str,
    screen_sort: str,
    page: int,
    per_page: int,
    pii_filter: str,
    color_filter: str,
) -> list[dict]:
    """Return paginated screen rows cached in Redis."""
    if screen_sort == "added_desc":
        order_by = CuratedDatasetItem.selected_at.desc()
    elif screen_sort == "added_asc":
        order_by = CuratedDatasetItem.selected_at.asc()
    else:
        order_by = CuratedDatasetItem.task_id.asc()

    offset = (page - 1) * per_page
    with get_db_session() as db:
        query = (
            db.query(
                CuratedDatasetItem.task_id.label("task_id"),
                CuratedDatasetItem.include_in_export.label("include_in_export"),
                CuratedDatasetItem.selected_at.label("selected_at"),
                CuratedDatasetItem.selection_method.label("selection_method"),
                DirectImageUpload.edited_filename.label("edited_filename"),
            )
            .join(GradingTask, GradingTask.id == CuratedDatasetItem.task_id)
            .outerjoin(EncounterFile, GradingTask.encounter_file_id == EncounterFile.id)
            .outerjoin(DirectImageUpload, GradingTask.direct_image_upload_id == DirectImageUpload.id)
            .filter(CuratedDatasetItem.dataset_id == dataset_id)
        )
        query = _apply_pii_filter(query, pii_filter)
        query = _apply_color_filter(query, color_filter)
        items = query.order_by(order_by).offset(offset).limit(per_page).all()
    return _build_screen_page_rows(db, items, disease_id, final_grade_basis, offset)


def _clear_dataset_screen_cache() -> None:
    cache.delete_memoized(_get_dataset_screen_page_cached)


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
        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
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

        db_user = (
            db.query(User)
            .options(joinedload(User.roles))
            .filter(User.id == current_user.id)
            .first()
        )
        user_roles = {r.name for r in (db_user.roles or [])} if db_user else set()

        screen_sort = request.args.get("sort", "task_asc")
        if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
            screen_sort = "task_asc"
        page = request.args.get("page", 1, type=int)
        pii_filter = request.args.get("pii_filter", "all")
        if pii_filter not in {"all", "detected"}:
            pii_filter = "all"
        color_filter = request.args.get("color_filter", "all")
        if color_filter not in {"all", "color", "grayscale"}:
            color_filter = "all"
        per_page = 50

        decided_task_ids = {
            task_id
            for (task_id,) in db.query(CuratedDatasetItem.task_id)
            .filter(CuratedDatasetItem.dataset_id == dataset.id)
            .all()
        }
        # Evaluate total matches for the stored filters
        matching_rows = _fetch_filtered_rows(filters)
        total_matching = len(matching_rows)

        total_screen = _count_dataset_items(db, dataset.id, pii_filter, color_filter)

        include_count = _count_dataset_items_by_export_state(db, dataset.id, pii_filter, color_filter, True)
        exclude_count = _count_dataset_items_by_export_state(db, dataset.id, pii_filter, color_filter, False)

        total_pages = max(1, (total_screen + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))

        screen_rows = _get_dataset_screen_page_cached(
            dataset.id,
            dataset.disease_id,
            normalize_final_grade_basis(filters.get("final_grade_basis")),
            screen_sort,
            page,
            per_page,
            pii_filter,
            color_filter,
        )
        included_display = [row for row in screen_rows if not row["is_excluded"]]
        excluded_display = [row for row in screen_rows if row["is_excluded"]]

        if request.method == "POST":
            if dataset.is_finalized:
                flash("Dataset is finalized and cannot be edited.", "warning")
                return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))
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
                _clear_dataset_screen_cache()
                decided_task_ids.add(task_id)
                flash("Decision saved.", "success")
                return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        selected_task_id = request.args.get("selected_task_id", type=int)
        selected_row = None
        selected_image = None
        if selected_task_id:
            selected_item = (
                db.query(CuratedDatasetItem)
                .filter(
                    CuratedDatasetItem.dataset_id == dataset.id,
                    CuratedDatasetItem.task_id == selected_task_id,
                    CuratedDatasetItem.include_in_export.is_(True),
                )
                .first()
            )
            if selected_item:
                task_query = (
                    db.query(GradingTask)
                    .filter(GradingTask.id == selected_task_id)
                    .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
                )
                task_query = scope(db, task_query, GradingTask, current_user, 'dataset.curation.view')
                selected_task = task_query.first()
                if selected_task:
                    selected_image = selected_task.encounter_file or selected_task.direct_image
                    selected_rows = _fetch_rows_by_task_ids(
                        [selected_task_id],
                        dataset.disease_id,
                        normalize_final_grade_basis(filters.get("final_grade_basis")),
                    )
                    selected_row = selected_rows[0] if selected_rows else None

        next_row = None if dataset.is_finalized else _get_next_pending_row(filters, decided_task_ids)
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

        active_share = (
            db.query(DatasetShare)
            .filter(DatasetShare.dataset_id == dataset.id, DatasetShare.is_active.is_(True))
            .order_by(DatasetShare.created_at.desc())
            .first()
        )
        total_downloads = (
            db.query(sa.func.coalesce(sa.func.sum(DatasetShare.download_count), 0))
            .filter(DatasetShare.dataset_id == dataset.id)
            .scalar()
        )
        total_downloads = int(total_downloads or 0)
        now = datetime.now(timezone.utc)
        can_finalize = ("dataset_creator" in user_roles or "admin" in user_roles or current_user.is_master_admin) and not dataset.is_finalized
        can_unfinalize = False
        override_required = False
        within_window = False
        is_creator = False
        is_admin = "admin" in user_roles or current_user.is_master_admin
        if dataset.is_finalized and dataset.finalized_at:
            within_window = (now - dataset.finalized_at) <= timedelta(minutes=30)
            is_creator = dataset.finalized_by_user_id == current_user.id
            can_unfinalize = (within_window and is_creator) or is_admin
            override_required = bool(is_admin and not (within_window and is_creator))

        share_display = session.pop("dataset_share_display", None)
        if share_display and share_display.get("dataset_uuid") != dataset.uuid:
            share_display = None

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
            screen_rows=screen_rows,
            screen_sort=screen_sort,
            pii_filter=pii_filter,
            color_filter=color_filter,
            screen_total=total_screen,
            screen_page=page,
            screen_total_pages=total_pages,
            screen_has_prev=page > 1,
            screen_has_next=page < total_pages,
            can_share="dataset_creator" in user_roles,
            share_display=share_display,
            active_share=active_share,
            total_downloads=total_downloads,
            can_finalize=can_finalize,
            can_unfinalize=can_unfinalize,
            override_required=override_required,
            selected_task_id=selected_task_id,
            selected_row=selected_row,
            selected_image=selected_image,
        )


@bp.route("/dataset-curation/<dataset_uuid>/viewer/<string:image_uuid>")
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_screen_viewer(dataset_uuid: str, image_uuid: str):
    """Serve the screening viewer card for an included dataset image."""
    screen_sort = request.args.get("sort", "task_asc")
    if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
        screen_sort = "task_asc"
    pii_filter = request.args.get("pii_filter", "all")
    if pii_filter not in {"all", "detected"}:
        pii_filter = "all"
    color_filter = request.args.get("color_filter", "all")
    if color_filter not in {"all", "color", "grayscale"}:
        color_filter = "all"
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = {lu.id for lu in lab_units_query.all()}
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(allowed_lab_units) and not current_user.is_master_admin:
            return ("Forbidden", 403)

        query = (
            db.query(GradingTask)
            .join(CuratedDatasetItem, CuratedDatasetItem.task_id == GradingTask.id)
            .filter(
                CuratedDatasetItem.dataset_id == dataset.id,
                sa.or_(
                    GradingTask.encounter_file.has(uuid=image_uuid),
                    GradingTask.direct_image.has(uuid=image_uuid),
                ),
            )
            .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
        )
        query = scope(db, query, GradingTask, current_user, 'dataset.curation.view')
        task = query.first()
        if not task:
            return ("Not found", 404)

        dataset_item = (
            db.query(CuratedDatasetItem)
            .filter(CuratedDatasetItem.dataset_id == dataset.id, CuratedDatasetItem.task_id == task.id)
            .first()
        )
        is_excluded = bool(dataset_item and not dataset_item.include_in_export)
        index = None
        if dataset_item:
            if screen_sort == "added_asc":
                order_by = CuratedDatasetItem.selected_at.asc()
            elif screen_sort == "added_desc":
                order_by = CuratedDatasetItem.selected_at.desc()
            else:
                order_by = CuratedDatasetItem.task_id.asc()
            all_items = (
                db.query(CuratedDatasetItem.task_id)
                .filter(CuratedDatasetItem.dataset_id == dataset.id)
                .order_by(order_by)
                .all()
            )
            ordered_ids = [i.task_id for i in all_items]
            if task.id in ordered_ids:
                index = ordered_ids.index(task.id) + 1

        image_obj = task.encounter_file or task.direct_image
        display_rows = _fetch_rows_by_task_ids(
            [task.id],
            dataset.disease_id,
            normalize_final_grade_basis(stored_filters.get("final_grade_basis")),
        )
        display_row = display_rows[0] if display_rows else None
        variant = "orig"
        if task.direct_image and task.direct_image.edited_filename:
            variant = "edited"
        meta = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == str(image_uuid),
                ImageMetadata.image_variant == variant,
            )
            .first()
        )
        metadata_payload = None
        if meta:
            metadata_payload = {
                "width": meta.width,
                "height": meta.height,
                "format": meta.format,
                "mode": meta.mode,
                "is_grayscale": meta.is_grayscale,
                "has_alpha": meta.has_alpha,
                "dpi_x": meta.dpi_x,
                "dpi_y": meta.dpi_y,
                "avg_luminance": meta.avg_luminance,
                "max_luminance": meta.max_luminance,
                "luminance_std": meta.luminance_std,
                "mean_r": meta.mean_r,
                "mean_g": meta.mean_g,
                "mean_b": meta.mean_b,
                "median_r": meta.median_r,
                "median_g": meta.median_g,
                "median_b": meta.median_b,
                "file_size_bytes": meta.file_size_bytes,
                "exif_present": bool(meta.exif_json),
                "iptc_present": bool(meta.iptc_json),
                "size_ok": bool(meta.width and meta.height and meta.width >= 1024 and meta.height >= 768),
            }

        return render_template(
            "review/_dataset_screen_viewer.html",
            dataset=dataset,
            image=image_obj,
            image_uuid=image_uuid,
            row=display_row,
            metadata=metadata_payload,
            image_variant=variant,
            is_excluded=is_excluded,
            browse_index=index,
            screen_sort=screen_sort,
            pii_filter=pii_filter,
            color_filter=color_filter,
        )


@bp.route("/dataset-curation/<dataset_uuid>/screen-gallery", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_screen_gallery(dataset_uuid: str):
    """Return a paginated thumbnail gallery for screening."""
    page = request.args.get("page", 1, type=int)
    screen_sort = request.args.get("sort", "task_asc")
    if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
        screen_sort = "task_asc"
    pii_filter = request.args.get("pii_filter", "all")
    if pii_filter not in {"all", "detected"}:
        pii_filter = "all"
    color_filter = request.args.get("color_filter", "all")
    if color_filter not in {"all", "color", "grayscale"}:
        color_filter = "all"
    per_page = 25
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            return ("Forbidden", 403)

        total = _count_dataset_items(db, dataset.id, pii_filter, color_filter)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page

        if screen_sort == "added_asc":
            order_by = CuratedDatasetItem.selected_at.asc()
        elif screen_sort == "added_desc":
            order_by = CuratedDatasetItem.selected_at.desc()
        else:
            order_by = CuratedDatasetItem.task_id.asc()

        query = (
            db.query(
                CuratedDatasetItem.task_id.label("task_id"),
                CuratedDatasetItem.include_in_export.label("include_in_export"),
                CuratedDatasetItem.selected_at.label("selected_at"),
                CuratedDatasetItem.selection_method.label("selection_method"),
                DirectImageUpload.edited_filename.label("edited_filename"),
            )
            .join(GradingTask, GradingTask.id == CuratedDatasetItem.task_id)
            .outerjoin(EncounterFile, GradingTask.encounter_file_id == EncounterFile.id)
            .outerjoin(DirectImageUpload, GradingTask.direct_image_upload_id == DirectImageUpload.id)
            .filter(CuratedDatasetItem.dataset_id == dataset.id)
        )
        query = _apply_pii_filter(query, pii_filter)
        query = _apply_color_filter(query, color_filter)
        items = query.order_by(order_by).offset(offset).limit(per_page).all()
        page_rows = _build_screen_page_rows(
            db,
            items,
            dataset.disease_id,
            normalize_final_grade_basis(stored_filters.get("final_grade_basis")),
            offset,
        )

        return render_template(
            "review/_dataset_screen_gallery.html",
            dataset=dataset,
            rows=page_rows,
            page=page,
            total_pages=total_pages,
            screen_sort=screen_sort,
            pii_filter=pii_filter,
            color_filter=color_filter,
            has_prev=page > 1,
            has_next=page < total_pages,
        )


@bp.route("/dataset-curation/<dataset_uuid>/screen-list", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_screen_list(dataset_uuid: str):
    """Return a paginated list for screening without a full page reload."""
    page = request.args.get("page", 1, type=int)
    screen_sort = request.args.get("sort", "task_asc")
    if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
        screen_sort = "task_asc"
    pii_filter = request.args.get("pii_filter", "all")
    if pii_filter not in {"all", "detected"}:
        pii_filter = "all"
    color_filter = request.args.get("color_filter", "all")
    if color_filter not in {"all", "color", "grayscale"}:
        color_filter = "all"
    per_page = 50
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            return ("Forbidden", 403)

        total_screen = _count_dataset_items(db, dataset.id, pii_filter, color_filter)
        total_pages = max(1, (total_screen + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))

        screen_rows = _get_dataset_screen_page_cached(
            dataset.id,
            dataset.disease_id,
            normalize_final_grade_basis(stored_filters.get("final_grade_basis")),
            screen_sort,
            page,
            per_page,
            pii_filter,
            color_filter,
        )
        include_count = _count_dataset_items_by_export_state(db, dataset.id, pii_filter, color_filter, True)
        exclude_count = _count_dataset_items_by_export_state(db, dataset.id, pii_filter, color_filter, False)

        return render_template(
            "review/_dataset_screen_list.html",
            dataset=dataset,
            screen_rows=screen_rows,
            screen_sort=screen_sort,
            pii_filter=pii_filter,
            color_filter=color_filter,
            screen_total=total_screen,
            screen_page=page,
            screen_total_pages=total_pages,
            screen_has_prev=page > 1,
            screen_has_next=page < total_pages,
            include_count=include_count,
            exclude_count=exclude_count,
        )


@bp.route("/dataset-curation/<dataset_uuid>/toggle-item", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_toggle_item(dataset_uuid: str):
    """Toggle include/exclude for a dataset item and return updated viewer."""
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)
        if dataset.is_finalized:
            return ("Dataset is finalized.", 409)
        stored_filters = json.loads(dataset.filters_json or "{}")

        task_id = request.form.get("task_id", type=int)
        if not task_id:
            return ("Missing task", 400)

        item = (
            db.query(CuratedDatasetItem)
            .filter(CuratedDatasetItem.dataset_id == dataset.id, CuratedDatasetItem.task_id == task_id)
            .first()
        )
        if not item:
            return ("Not found", 404)

        item.include_in_export = not item.include_in_export
        item.selection_method = "manual"
        item.selected_by_user_id = current_user.id
        db.add(item)

        task_query = (
            db.query(GradingTask)
            .filter(GradingTask.id == task_id)
            .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
        )
        task_query = scope(db, task_query, GradingTask, current_user, 'dataset.curation.view')
        task = task_query.first()
        if not task:
            return ("Not found", 404)

        image_uuid = task.encounter_file.uuid if task.encounter_file else task.direct_image.uuid
        display_rows = _fetch_rows_by_task_ids(
            [task.id],
            dataset.disease_id,
            normalize_final_grade_basis(stored_filters.get("final_grade_basis")),
        )
        display_row = display_rows[0] if display_rows else None
        all_items = (
            db.query(CuratedDatasetItem.task_id)
            .filter(CuratedDatasetItem.dataset_id == dataset.id)
            .all()
        )
        ordered_ids = sorted([i.task_id for i in all_items])
        index = ordered_ids.index(task.id) + 1 if task.id in ordered_ids else None
        image_kind = "encounter" if task.encounter_file else "direct"
        variant = "orig"
        if task.direct_image and task.direct_image.edited_filename:
            variant = "edited"
        meta = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == str(image_uuid),
                ImageMetadata.image_variant == variant,
            )
            .first()
        )
        metadata_payload = None
        if meta:
            metadata_payload = {
                "width": meta.width,
                "height": meta.height,
                "format": meta.format,
                "mode": meta.mode,
                "is_grayscale": meta.is_grayscale,
                "has_alpha": meta.has_alpha,
                "dpi_x": meta.dpi_x,
                "dpi_y": meta.dpi_y,
                "avg_luminance": meta.avg_luminance,
                "max_luminance": meta.max_luminance,
                "luminance_std": meta.luminance_std,
                "mean_r": meta.mean_r,
                "mean_g": meta.mean_g,
                "mean_b": meta.mean_b,
                "median_r": meta.median_r,
                "median_g": meta.median_g,
                "median_b": meta.median_b,
                "file_size_bytes": meta.file_size_bytes,
                "exif_present": bool(meta.exif_json),
                "iptc_present": bool(meta.iptc_json),
                "size_ok": bool(meta.width and meta.height and meta.width >= 1024 and meta.height >= 768),
            }
        row_update = {
            "task_id": task.id,
            "image_uuid": image_uuid,
            "image_kind": image_kind,
            "image_variant": variant,
            "final_impression": display_row.final_impression if display_row else None,
            "is_excluded": not item.include_in_export,
            "metadata": metadata_payload,
            "index": index,
            "selected_at": item.selected_at,
            "selection_method": item.selection_method,
        }
        _clear_dataset_screen_cache()

        if (request.headers.get("HX-Target") or "").startswith("datasetScreenThumb-"):
            page_value = request.form.get("page")
            try:
                page = int(page_value) if page_value else 1
            except (TypeError, ValueError):
                page = 1
            screen_sort = request.form.get("sort") or "task_asc"
            if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
                screen_sort = "task_asc"
            return render_template(
                "review/_dataset_screen_thumb.html",
                dataset=dataset,
                row=row_update,
                page=page,
                screen_sort=screen_sort,
            )

        screen_sort = request.form.get("sort") or "task_asc"
        if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
            screen_sort = "task_asc"
        pii_filter = request.form.get("pii_filter") or "all"
        if pii_filter not in {"all", "detected"}:
            pii_filter = "all"
        color_filter = request.form.get("color_filter") or "all"
        if color_filter not in {"all", "color", "grayscale"}:
            color_filter = "all"
        total_screen = _count_dataset_items(db, dataset.id, pii_filter, color_filter)
        include_count = _count_dataset_items_by_export_state(db, dataset.id, pii_filter, color_filter, True)
        exclude_count = _count_dataset_items_by_export_state(db, dataset.id, pii_filter, color_filter, False)
        return render_template(
            "review/_dataset_screen_viewer.html",
            dataset=dataset,
            image=task.encounter_file or task.direct_image,
            image_uuid=image_uuid,
            row=display_row,
            metadata=metadata_payload,
            image_variant=variant,
            is_excluded=not item.include_in_export,
            row_update=row_update,
            browse_index=index,
            screen_sort=screen_sort,
            pii_filter=pii_filter,
            color_filter=color_filter,
            screen_total=total_screen,
            include_count=include_count,
            exclude_count=exclude_count,
        )


@bp.route("/dataset-curation/<dataset_uuid>/add-more", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator", "analytics_viewer")
def dataset_add_more(dataset_uuid: str):
    """Add one random matching task to the dataset."""
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)
        if dataset.is_finalized:
            flash("Dataset is finalized and cannot be edited.", "warning")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have access to the lab units for this dataset.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        filters = _filters_with_allowed(stored_filters, allowed_lab_units)
        rows = _fetch_filtered_rows(filters)
        decided_task_ids = {
            row[0]
            for row in (
                db.query(CuratedDatasetItem.task_id)
                .filter(CuratedDatasetItem.dataset_id == dataset.id)
                .all()
            )
        }
        candidates = [row for row in rows if row.task_id not in decided_task_ids]
        if not candidates:
            flash("No more matching tasks are available to add.", "info")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        picked = random.choice(candidates)
        selected_at = utcnow()
        db.add(
            CuratedDatasetItem(
                dataset_id=dataset.id,
                task_id=picked.task_id,
                include_in_export=True,
                selection_method="auto",
                selected_by_user_id=current_user.id,
                selected_at=selected_at,
            )
        )
        flash("Added one more task to the dataset.", "success")
        _clear_dataset_screen_cache()
        if request.headers.get("HX-Request") == "true":
            screen_sort = request.form.get("sort") or "task_asc"
            if screen_sort not in {"task_asc", "added_asc", "added_desc"}:
                screen_sort = "task_asc"
            if screen_sort == "added_asc":
                order_by = CuratedDatasetItem.selected_at.asc()
            elif screen_sort == "added_desc":
                order_by = CuratedDatasetItem.selected_at.desc()
            else:
                order_by = CuratedDatasetItem.task_id.asc()
            ordered_ids = [
                row.task_id
                for row in (
                    db.query(CuratedDatasetItem.task_id)
                    .filter(CuratedDatasetItem.dataset_id == dataset.id)
                    .order_by(order_by)
                    .all()
                )
            ]
            index = ordered_ids.index(picked.task_id) + 1 if picked.task_id in ordered_ids else None
            next_task_id = None
            if index and index < len(ordered_ids):
                next_task_id = ordered_ids[index]
            next_image_uuid = None
            if next_task_id:
                next_rows = _fetch_rows_by_task_ids(
                    [next_task_id],
                    dataset.disease_id,
                    normalize_final_grade_basis(filters.get("final_grade_basis")),
                )
                if next_rows:
                    next_image_uuid = next_rows[0].encounter_file_uuid or next_rows[0].direct_image_uuid
            image_uuid = picked.encounter_file_uuid or picked.direct_image_uuid
            image_kind = "encounter" if picked.encounter_file_uuid else "direct"
            oob_swap = None
            if next_image_uuid:
                oob_swap = f"beforebegin:#datasetScreenRow-{next_image_uuid}"
            else:
                oob_swap = "beforeend:#datasetScreenList"
            row_payload = {
                "task_id": picked.task_id,
                "image_uuid": image_uuid,
                "image_kind": image_kind,
                "final_impression": picked.final_impression,
                "is_excluded": False,
                "index": index,
                "selected_at": selected_at,
                "selection_method": "auto",
            }
            response = make_response(
                render_template(
                    "review/_dataset_screen_row.html",
                    dataset=dataset,
                    row=row_payload,
                    oob_swap=oob_swap,
                    row_is_new=True,
                    screen_sort=screen_sort,
                )
            )
            response.headers["HX-Trigger"] = json.dumps(
                {"datasetAddMore": {"image_uuid": image_uuid}}
            )
            return response
        return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid, selected_task_id=picked.task_id))



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
        if not dataset.is_finalized:
            flash("Finalize the dataset before exporting.", "warning")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        # Get allowed lab units via scoped query
        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
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
        job = db.query(Job).filter(Job.token == job_token).first()
        if job:
            db.add(
                DatasetExport(
                    dataset_id=dataset.id,
                    job_id=job.id,
                    created_by_user_id=uploader_user_id,
                )
            )
            db.flush()

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


@bp.route("/dataset-curation/<dataset_uuid>/share", methods=["POST"])
@roles_required("dataset_creator")
def dataset_share_create(dataset_uuid: str):
    """Create or regenerate a dataset share token + OTP."""
    logger = logging.getLogger("audit")
    share_display_data = None
    link_email_failed = False
    otp_email_failed = False
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)
        if not dataset.is_finalized:
            flash("Finalize the dataset before sharing.", "warning")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have permission to share this dataset.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        purpose = (request.form.get("share_purpose") or "").strip()
        created_for = (request.form.get("share_created_for") or "").strip()
        recipient_email = (request.form.get("share_recipient_email") or "").strip()
        expiry_hours = request.form.get("share_expiry_hours", type=int) or 24
        expiry_hours = max(1, min(168, expiry_hours))

        if not purpose or not created_for:
            flash("Purpose and created-for are required.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))
        if recipient_email and not validate_email(recipient_email):
            flash("Recipient email is invalid.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        token = generate_share_token()
        otp = generate_share_otp()
        token_hash = hash_share_token(token)
        otp_hash = hash_share_otp(otp)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        share = DatasetShare(
            dataset_id=dataset.id,
            token_hash=token_hash,
            otp_hash=otp_hash,
            purpose=purpose,
            created_for=created_for,
            recipient_email=recipient_email or None,
            expires_at=expires_at,
            created_by_user_id=current_user.id,
            is_active=True,
        )
        db.add(share)
        db.flush()

        share_display_data = {
            "dataset_uuid": dataset.uuid,
            "token": token,
            "otp": otp,
            "expires_at": expires_at.isoformat(),
        }
        logger.info(
            "Dataset share created dataset_id=%s dataset_uuid=%s user_id=%s expires_at=%s",
            dataset.id,
            dataset.uuid,
            current_user.id,
            expires_at.isoformat(),
        )
        main_admin_email = None
        main_admin = db.query(User).filter(User.username == "main_admin").first()
        if main_admin and main_admin.email:
            main_admin_email = main_admin.email.strip()
        if recipient_email:
            cc_list = []
            if main_admin_email and main_admin_email.lower() != recipient_email.lower():
                cc_list.append(main_admin_email)
            link = url_for("datasets.download_welcome", token=token, _external=True)
            subject = f"Dataset download link: {dataset.name}"
            body = "\n".join(
                [
                    f"Dataset: {dataset.name}",
                    f"Purpose: {dataset.purpose}",
                    f"Created for: {created_for}",
                    "Download link:",
                    link,
                    "",
                    f"Expires at: {expires_at.isoformat()}",
                    "",
                    "OTP will be shared separately by the dataset creator.",
                ]
            )
            logo_cid, inline_images = build_inline_logo_image()
            html_body = build_dataset_share_email_html(
                title="Dataset Download Link",
                dataset_name=dataset.name,
                purpose=dataset.purpose,
                created_for=created_for,
                expires_at=expires_at.isoformat(),
                logo_cid=logo_cid,
                link=link,
                link_note="OTP will be shared separately by the dataset creator.",
            )
            try:
                send_email(
                    recipient_email,
                    subject,
                    body,
                    sensitive=True,
                    cc_emails=cc_list or None,
                    html_body=html_body,
                    inline_images=inline_images,
                )
            except Exception as exc:
                logger.warning("Share link email failed: %s", exc)
                link_email_failed = True
        creator_email = (current_user.email or "").strip()
        if creator_email:
            cc_list = []
            if main_admin_email and main_admin_email.lower() != creator_email.lower():
                cc_list.append(main_admin_email)
            otp_subject = f"Dataset share OTP: {dataset.name}"
            otp_body = "\n".join(
                [
                    f"Dataset: {dataset.name}",
                    f"Purpose: {dataset.purpose}",
                    f"Created for: {created_for}",
                    f"Expires at: {expires_at.isoformat()}",
                    "",
                    f"OTP: {otp}",
                    "",
                    "Kindly share the OTP securely with the dataset recipient.",
                ]
            )
            logo_cid, inline_images = build_inline_logo_image()
            otp_html = build_dataset_share_email_html(
                title="Dataset Share OTP",
                dataset_name=dataset.name,
                purpose=dataset.purpose,
                created_for=created_for,
                expires_at=expires_at.isoformat(),
                logo_cid=logo_cid,
                otp=otp,
            )
            try:
                send_email(
                    creator_email,
                    otp_subject,
                    otp_body,
                    sensitive=True,
                    cc_emails=cc_list or None,
                    html_body=otp_html,
                    inline_images=inline_images,
                )
            except Exception as exc:
                logger.warning("Share OTP email failed: %s", exc)
                otp_email_failed = True
    if share_display_data:
        session["dataset_share_display"] = share_display_data
        session.modified = True
        flash("Share link created. Save the OTP now; it will not be shown again.", "success")
        if link_email_failed:
            flash("Link email failed to send. Please share the link manually.", "warning")
        if otp_email_failed:
            flash("OTP email failed to send. Please share the OTP manually.", "warning")
    return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))


@bp.route("/dataset-curation/<dataset_uuid>/finalize", methods=["POST"])
@roles_required("dataset_creator", "admin")
def dataset_finalize(dataset_uuid: str):
    """Finalize a dataset to lock selections."""
    logger = logging.getLogger("audit")
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)
        if dataset.is_finalized:
            flash("Dataset is already finalized.", "info")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have permission to finalize this dataset.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        dataset.is_finalized = True
        dataset.finalized_at = datetime.now(timezone.utc)
        dataset.finalized_by_user_id = current_user.id
        db.add(dataset)
        logger.info(
            "Dataset finalized dataset_id=%s dataset_uuid=%s user_id=%s",
            dataset.id,
            dataset.uuid,
            current_user.id,
        )
        flash("Dataset finalized.", "success")
        return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))


@bp.route("/dataset-curation/<dataset_uuid>/unfinalize", methods=["POST"])
@roles_required("dataset_creator", "admin")
def dataset_unfinalize(dataset_uuid: str):
    """Unfinalize a dataset within a limited window or as admin."""
    logger = logging.getLogger("audit")
    with get_db_session() as db:
        dataset = (
            db.query(CuratedDataset)
            .filter(CuratedDataset.uuid == dataset_uuid, CuratedDataset.is_active.is_(True))
            .first()
        )
        if not dataset:
            abort(404)
        if not dataset.is_finalized:
            flash("Dataset is not finalized.", "info")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
        allowed_lab_units = [lu.id for lu in lab_units_query.all()]
        stored_filters = json.loads(dataset.filters_json or "{}")
        stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
        if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)) and not current_user.is_master_admin:
            flash("You do not have permission to unfinalize this dataset.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))

        now = datetime.now(timezone.utc)
        within_window = bool(dataset.finalized_at and (now - dataset.finalized_at) <= timedelta(minutes=30))
        is_creator = dataset.finalized_by_user_id == current_user.id
        is_admin = current_user.has_role("admin") or current_user.is_master_admin
        if not ((within_window and is_creator) or is_admin):
            flash("Unfinalize window expired. Contact an admin.", "error")
            return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))
        override_used = bool(is_admin and not (within_window and is_creator))

        dataset.is_finalized = False
        dataset.finalized_at = None
        dataset.finalized_by_user_id = None
        db.add(dataset)
        deactivated_shares = (
            db.query(DatasetShare)
            .filter(DatasetShare.dataset_id == dataset.id, DatasetShare.is_active.is_(True))
            .update({"is_active": False})
        )
        logger.info(
            "Dataset unfinalized dataset_id=%s dataset_uuid=%s user_id=%s override=%s shares_deactivated=%s",
            dataset.id,
            dataset.uuid,
            current_user.id,
            override_used,
            deactivated_shares,
        )
        if deactivated_shares:
            flash("Dataset unfinalized. Existing shares were deactivated.", "warning")
        else:
            flash("Dataset unfinalized. You can edit selections again.", "warning")
        return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset_uuid))



@bp.route("/dataset-export/<job_token>/<path:filename>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "data_exporter", "dataset_creator")
def dataset_export_download(job_token: str, filename: str):
    """Serve dataset export artifacts."""
    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_token, Job.upload_type == "dataset_export").first()
        if not job:
            abort(404)
        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
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
        lab_units_query = scope(db, db.query(LabUnit), LabUnit, current_user, 'dataset.curation.view')
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
