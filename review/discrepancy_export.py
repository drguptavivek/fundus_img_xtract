from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from sqlalchemy import and_, or_, text

from job_store import db_set_item_state, db_set_job_status
from models import (
    BASE_DIR,
    IMAGE_DIR,
    Disease,
    DiseaseGrading,
    Grade,
    LabUnit,
    GradingTask,
    EncounterFile,
    PatientEncounters,
    DirectImageUpload,
    DIRECT_UPLOAD_DIR,
)
from db_transaction_manager import get_db_session
from utils.fileUtils import abs_from_parts

EXPORT_DIR = BASE_DIR / "files" / "exports"
MAX_ROWS_PER_ZIP = 200
MAX_BYTES_PER_ZIP = 200 * 1024 * 1024  # 200 MB
EXPORT_RETENTION_HOURS = 24


@dataclass
class ExportTaskRow:
    task_id: int
    task_uuid: str
    disease: str
    lab_unit: str
    hospital: str
    state: str
    consensus_status: Optional[str]
    consensus_method: Optional[str]
    final_impression: Optional[str]
    grading_details_json: str
    ai_review_comments: List[str]
    ai_review_statuses: List[str]
    encounter_file_id: Optional[int]
    encounter_file_uuid: Optional[str]
    encounter_filename: Optional[str]
    encounter_upload_date: Optional[datetime]
    direct_image_upload_id: Optional[int]
    direct_image_uuid: Optional[str]
    direct_filename: Optional[str]
    direct_folder_rel: Optional[str]


def enqueue_discrepancy_export(app, job_token: str, filters: Dict[str, Any], user_context: Dict[str, Any]) -> None:
    from utils.celery_helpers import enqueue_task, celery_enabled
    if celery_enabled():
        enqueue_task(
            "celery_tasks.tasks.export_tasks.run_discrepancy_export_task",
            job_token,
            filters,
            user_context,
            user_id=user_context.get("user_id") if user_context else None,
            hospital_id=user_context.get("hospital_id") if user_context else None,
        )
        return
    executor = app.config["EXECUTOR"]
    executor.submit(_run_export_job, app, job_token, filters, user_context)


def enqueue_dataset_export(
    app,
    job_token: str,
    dataset_id: int,
    task_ids: Sequence[int],
    metadata: Dict[str, Any] | None = None,
) -> None:
    """Queue export for a curated dataset using explicit task ids."""
    from utils.celery_helpers import enqueue_task, celery_enabled
    if celery_enabled():
        enqueue_task(
            "celery_tasks.tasks.export_tasks.run_dataset_export_task",
            job_token,
            dataset_id,
            list(task_ids),
            metadata or {},
            user_id=metadata.get("user_id") if metadata else None,
            hospital_id=metadata.get("hospital_id") if metadata else None,
        )
        return
    executor = app.config["EXECUTOR"]
    executor.submit(_run_dataset_export_job, app, job_token, dataset_id, list(task_ids), metadata or {})


def _cleanup_old_exports() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=EXPORT_RETENTION_HOURS)
    if not EXPORT_DIR.exists():
        return
    for child in EXPORT_DIR.iterdir():
        try:
            if child.is_dir():
                mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
        except Exception:
            continue


def run_discrepancy_export_job(job_token: str, filters: Dict[str, Any], user_context: Dict[str, Any]) -> None:
    db_set_job_status(job_token, "processing")
    db_set_item_state(job_token, "discrepancy_export", "processing")

    try:
        _cleanup_old_exports()
        rows = _fetch_filtered_rows(filters)
        if not rows:
            db_set_job_status(job_token, "error", error="No tasks match filters")
            db_set_item_state(job_token, "discrepancy_export", "error", "No tasks match filters")
            return

        export_dir = EXPORT_DIR / job_token
        export_dir.mkdir(parents=True, exist_ok=True)

        graded_rows = _build_task_payload(rows)
        excel_path = _write_excel(graded_rows, filters, export_dir)
        _write_grading_scheme(filters.get("disease_id"), export_dir)
        zip_paths, warnings = _write_zips(graded_rows, export_dir)

        if warnings:
            (export_dir / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")

        db_set_job_status(job_token, "done")
        db_set_item_state(job_token, "discrepancy_export", "completed", f"excel={excel_path.name}; zips={','.join(p.name for p in zip_paths)}")
    except Exception as exc:
        db_set_job_status(job_token, "error", error=str(exc))
        db_set_item_state(job_token, "discrepancy_export", "error", str(exc))


def run_dataset_export_job(
    job_token: str,
    dataset_id: int,
    task_ids: Sequence[int],
    metadata: Dict[str, Any],
) -> None:
    """Export a curated dataset using existing discrepancy export pipeline."""
    db_set_job_status(job_token, "processing")
    db_set_item_state(job_token, "dataset_export", "processing")

    try:
        _cleanup_old_exports()
        rows = _fetch_rows_by_task_ids(task_ids, metadata.get("disease_id"))
        if not rows:
            db_set_job_status(job_token, "error", error="No tasks to export")
            db_set_item_state(job_token, "dataset_export", "error", "No tasks to export")
            return

        export_dir = EXPORT_DIR / job_token
        export_dir.mkdir(parents=True, exist_ok=True)

        graded_rows = _build_task_payload(rows)
        export_filters = {"dataset_id": dataset_id, **(metadata or {})}
        excel_path = _write_excel(graded_rows, export_filters, export_dir, drop_ai_columns=True)
        _write_grading_scheme(metadata.get("disease_id"), export_dir)
        zip_paths, warnings = _write_zips(graded_rows, export_dir)

        if warnings:
            (export_dir / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")

        db_set_job_status(job_token, "done")
        db_set_item_state(
            job_token,
            "dataset_export",
            "completed",
            f"excel={excel_path.name}; zips={','.join(p.name for p in zip_paths)}",
        )
    except Exception as exc:
        db_set_job_status(job_token, "error", error=str(exc))
        db_set_item_state(job_token, "dataset_export", "error", str(exc))


def _run_export_job(app, job_token: str, filters: Dict[str, Any], user_context: Dict[str, Any]) -> None:
    with app.app_context():
        run_discrepancy_export_job(job_token, filters, user_context)


def _run_dataset_export_job(
    app,
    job_token: str,
    dataset_id: int,
    task_ids: Sequence[int],
    metadata: Dict[str, Any],
) -> None:
    with app.app_context():
        run_dataset_export_job(job_token, dataset_id, task_ids, metadata)


def _fetch_filtered_rows(filters: Dict[str, Any]) -> List[ExportTaskRow]:
    with get_db_session() as db:
        disease_id = filters.get("disease_id")
        lab_unit_id = filters.get("lab_unit_id")
        resident_grades = filters.get("resident_grade", [])
        resident2_grades = filters.get("resident2_grade", [])
        arbitrator_grades = filters.get("arbitrator_grade", [])
        final_grades = filters.get("final_grade", [])
        has_ai_grade = filters.get("has_ai_grade")
        has_review = filters.get("has_review")
        review_grades = filters.get("review_grade", [])
        has_consensus = filters.get("has_consensus", "has_consensus")
        ai_model_ids = filters.get("ai_model_id", [])
        ai_grades = filters.get("ai_grade", [])
        ai_review_statuses = filters.get("ai_review_status", [])
        allowed_lab_units: List[int] = filters.get("allowed_lab_units", [])
        if not allowed_lab_units:
            return []

        valid_grade_impressions: Set[str] = set()
        if disease_id:
            valid_grade_impressions = {
                row.impression
                for row in db.query(DiseaseGrading.impression)
                .filter(
                    DiseaseGrading.disease_id == disease_id,
                    DiseaseGrading.is_active.is_(True),
                )
                .all()
            }
        if valid_grade_impressions:
            resident_grades = [g for g in resident_grades if g in valid_grade_impressions]
            resident2_grades = [g for g in resident2_grades if g in valid_grade_impressions]
            arbitrator_grades = [g for g in arbitrator_grades if g in valid_grade_impressions]
            final_grades = [g for g in final_grades if g in valid_grade_impressions]
            review_grades = [g for g in review_grades if g in valid_grade_impressions]
            ai_grades = [g for g in ai_grades if g in valid_grade_impressions]

        disease_key = _resolve_disease_key(db, disease_id)
        mv_detail_col = f"{disease_key}_grading_details_json"
        mv_ai_count_col = f"{disease_key}_ai_grading_count"
        mv_consensus_col = f"{disease_key}_consensus_status"

        where_clauses = [
            "gt.disease_id = :disease_id",
            "gt.lab_unit_id = ANY(:allowed_lab_units)",
        ]
        params: Dict[str, Any] = {"disease_id": disease_id, "allowed_lab_units": allowed_lab_units}

        if lab_unit_id and lab_unit_id in allowed_lab_units:
            where_clauses.append("gt.lab_unit_id = :lab_unit_id")
            params["lab_unit_id"] = lab_unit_id

        require_final_grade = bool(filters.get("require_final_grade"))
        if has_consensus == "has_consensus":
            where_clauses.append("c.id IS NOT NULL")
            if require_final_grade:
                # Ensure a final grade is present (not just a consensus shell).
                where_clauses.append("c.final_disease_grading_id IS NOT NULL")
        elif has_consensus == "no":
            where_clauses.append("c.id IS NULL")

        if has_review == "yes":
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
            )
            valid_review_grades = [g for g in review_grades if g]
            if valid_review_grades:
                where_clauses.append(
                    f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                    "WHERE elem->>'role_slot' = 'review' AND elem->>'grade_name' = ANY(:review_grades))"
                )
                params["review_grades"] = valid_review_grades
        elif has_review == "no":
            where_clauses.append(
                f"NOT EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
            )

        if has_ai_grade == "yes":
            where_clauses.append(f"{mv_ai_count_col} > 0")
        elif has_ai_grade == "no":
            where_clauses.append(f"{mv_ai_count_col} = 0")
        else:
            ai_model_ids = []
            ai_grades = []
            ai_review_statuses = []

        role_grade_filters = [
            ("resident", resident_grades),
            ("resident2", resident2_grades),
            ("arbitrator", arbitrator_grades),
        ]
        for role, impressions in role_grade_filters:
            if impressions:
                valid = [g for g in impressions if g]
                if valid:
                    where_clauses.append(
                        f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                        "WHERE elem->>'role_slot' = :role_slot_"
                        + role
                        + " AND elem->>'grade_name' = ANY(:grade_names_"
                        + role
                        + "))"
                    )
                    params[f"role_slot_{role}"] = role
                    params[f"grade_names_{role}"] = valid

        selected_ai_model_id: Optional[int] = None
        if ai_model_ids:
            cleaned_models = [mid for mid in ai_model_ids if mid]
            if cleaned_models:
                selected_ai_model_id = int(cleaned_models[0])
                ai_model_ids = [str(selected_ai_model_id)]
            else:
                ai_model_ids = []

        if selected_ai_model_id is not None:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                "WHERE elem->>'role_slot' = 'ai' AND (elem->>'ai_model_id')::int = :ai_model_id)"
            )
            params["ai_model_id"] = selected_ai_model_id

        if ai_grades:
            valid_ai_grades = [g for g in ai_grades if g]
            if valid_ai_grades:
                where_clauses.append(
                    f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                    "WHERE elem->>'role_slot' = 'ai' AND elem->>'grade_name' = ANY(:ai_grade_names))"
                )
                params["ai_grade_names"] = valid_ai_grades

        if ai_review_statuses:
            valid_statuses = [s for s in ai_review_statuses if s]
            if valid_statuses:
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM grades g WHERE g.task_id = gt.id AND g.role_slot = 'ai' "
                    "AND g.ai_review_status = ANY(:ai_review_statuses))"
                )
                params["ai_review_statuses"] = valid_statuses

        if final_grades:
            valid_final_grades = [g for g in final_grades if g]
            if valid_final_grades:
                where_clauses.append("dg.impression = ANY(:final_grades)")
                params["final_grades"] = valid_final_grades

        # Dataset exclusivity: exclude tasks from selected existing datasets
        excluded_dataset_ids = filters.get("excluded_dataset_ids", [])
        if excluded_dataset_ids:
            where_clauses.append(
                "NOT EXISTS ("
                "SELECT 1 FROM curated_dataset_items cdi "
                "WHERE cdi.task_id = gt.id "
                "AND cdi.dataset_id = ANY(:excluded_dataset_ids) "
                "AND cdi.include_in_export = true"
                ")"
            )
            params["excluded_dataset_ids"] = excluded_dataset_ids

        # Handle random ordering
        randomize_selection = filters.get("randomize_selection", False)
        random_seed = filters.get("random_seed")

        if randomize_selection:
            if random_seed is not None:
                # Deterministic random: set seed once, then order by RANDOM().
                seed_value = random_seed / 2147483647.0
                db.execute(text("SELECT setseed(:seed)"), {"seed": seed_value})
                order_clause = "ORDER BY RANDOM()"
            else:
                # True random without seed
                order_clause = "ORDER BY RANDOM()"
        else:
            # Default: sequential by task_id descending
            order_clause = "ORDER BY gt.id DESC"

        where_sql = " AND ".join(where_clauses)

        base_query = f"""
            FROM mvw_image_listing_all v
            JOIN grading_tasks gt ON (
                (v.direct_image_upload_id IS NOT NULL AND gt.direct_image_upload_id = v.direct_image_upload_id) OR
                (v.encounter_file_id IS NOT NULL AND gt.encounter_file_id = v.encounter_file_id)
            )
            LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
            LEFT JOIN hospitals h ON lu.hospital_id = h.id
            LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
            LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id
            LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
            LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id
            LEFT JOIN consensus c ON gt.id = c.task_id
            LEFT JOIN disease_gradings dg ON c.final_disease_grading_id = dg.id
            WHERE {where_sql}
        """

        data_sql = f"""
            SELECT
                gt.id AS task_id,
                gt.uuid AS task_uuid,
                gt.state AS task_state,
                lu.name AS lab_unit_name,
                h.name AS hospital_name,
                {mv_detail_col} AS grading_details_json,
                {mv_consensus_col} AS consensus_status,
                {mv_ai_count_col} AS ai_grading_count,
                c.id AS consensus_id,
                dg.impression AS final_impression,
                c.method AS consensus_method,
                gt.encounter_file_id,
                ef.uuid AS encounter_file_uuid,
                ef.filename AS encounter_filename,
                zf.upload_date AS encounter_upload_date,
                gt.direct_image_upload_id,
                diu.uuid AS direct_image_uuid,
                diu.filename AS direct_filename,
                diu.folder_rel AS direct_folder_rel
            {base_query}
            {order_clause}
        """

        rows = db.execute(text(data_sql), params).fetchall()
        task_ids = [row.task_id for row in rows]

        ai_review_comments: Dict[int, List[str]] = {}
        ai_review_statuses: Dict[int, List[str]] = {}
        if task_ids:
            ai_review_rows = (
                db.query(Grade.task_id, Grade.ai_review_comment, Grade.ai_review_status)
                .filter(Grade.role_slot == "ai", Grade.task_id.in_(task_ids))
                .filter(or_(Grade.ai_review_comment.isnot(None), Grade.ai_review_status.isnot(None)))
                .all()
            )
            for task_id, comment, status in ai_review_rows:
                if comment:
                    ai_review_comments.setdefault(task_id, []).append(comment)
                if status:
                    ai_review_statuses.setdefault(task_id, []).append(status)

        results: List[ExportTaskRow] = []
        disease_map = {d.id: d.name for d in db.query(Disease).all()}
        disease_name = disease_map.get(disease_id, "")

        for row in rows:
            results.append(
                ExportTaskRow(
                    task_id=row.task_id,
                    task_uuid=str(row.task_uuid),
                    disease=disease_name,
                    lab_unit=row.lab_unit_name,
                    hospital=row.hospital_name,
                    state=row.task_state,
                    consensus_status=row.consensus_status,
                    consensus_method=row.consensus_method,
                    final_impression=row.final_impression,
                    grading_details_json=row.grading_details_json or "[]",
                    ai_review_comments=ai_review_comments.get(row.task_id, []),
                    ai_review_statuses=ai_review_statuses.get(row.task_id, []),
                    encounter_file_id=row.encounter_file_id,
                    encounter_file_uuid=row.encounter_file_uuid,
                    encounter_filename=row.encounter_filename,
                    encounter_upload_date=row.encounter_upload_date,
                    direct_image_upload_id=row.direct_image_upload_id,
                    direct_image_uuid=row.direct_image_uuid,
                    direct_filename=row.direct_filename,
                    direct_folder_rel=row.direct_folder_rel,
                )
            )

        return results


def _resolve_disease_key(db: Session, disease_id: int) -> str:
    if not disease_id:
        return "dr"
    disease = db.get(Disease, disease_id)
    if not disease:
        return "dr"
    name = (disease.name or "").lower()
    if "glaucoma" in name:
        return "glaucoma"
    if "amd" in name or "macular" in name:
        return "amd"
    return "dr"


def _extract_grades_by_role(details_json: str) -> Dict[str, Dict[str, Any]]:
    if isinstance(details_json, str):
        try:
            grades = json.loads(details_json)
        except Exception:
            return {}
    else:
        grades = details_json or []
    result: Dict[str, Dict[str, Any]] = {}
    for item in grades or []:
        role = item.get("role_slot")
        if not role:
            continue
        result[role] = {
            "impression": item.get("grade_name"),
            "comment": item.get("comment"),
            "selected_features": item.get("selected_features"),
            "ai_model_name": item.get("ai_model_name"),
            "ai_model_version": item.get("ai_model_version"),
            "ai_probability": item.get("ai_probability"),
        }
    return result


def _serialize_features_json(features: Any) -> Optional[str]:
    if features is None:
        return None
    if isinstance(features, str):
        return features
    if isinstance(features, list):
        labels: list[str] = []
        for item in features:
            if isinstance(item, dict):
                label = item.get("label")
                if label:
                    labels.append(str(label))
            elif isinstance(item, str):
                labels.append(item)
        if labels:
            return json.dumps(labels, ensure_ascii=True, separators=(",", ":"))
        return None
    try:
        return json.dumps(features, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        return None


def _build_task_payload(rows: Sequence[ExportTaskRow]) -> List[Dict[str, Any]]:
    encounter_ids = [r.encounter_file_id for r in rows if r.encounter_file_id]
    direct_ids = [r.direct_image_upload_id for r in rows if r.direct_image_upload_id]

    encounter_paths = _load_encounter_paths(encounter_ids) if encounter_ids else {}
    direct_paths = _load_direct_paths(direct_ids) if direct_ids else {}

    data: List[Dict[str, Any]] = []
    for row in rows:
        grades = _extract_grades_by_role(row.grading_details_json)
        ai_grade = grades.get("ai", {})
        ai_grade["ai_review_comments"] = row.ai_review_comments
        ai_grade["ai_review_statuses"] = row.ai_review_statuses
        grades["ai"] = ai_grade

        has_review = "review" in grades
        image_uuid = row.encounter_file_uuid or row.direct_image_uuid

        file_path: Optional[Path] = None
        renamed_filename: Optional[str] = None
        if row.encounter_file_id and row.encounter_file_id in encounter_paths:
            fp, ext = encounter_paths[row.encounter_file_id]
            file_path = fp
            renamed_filename = f"{image_uuid}{ext}"
        elif row.direct_image_upload_id and row.direct_image_upload_id in direct_paths:
            fp, ext = direct_paths[row.direct_image_upload_id]
            file_path = fp
            renamed_filename = f"{image_uuid}{ext}"

        data.append(
            {
                "task_id": row.task_id,
                "task_uuid": row.task_uuid,
                "disease": row.disease,
                "hospital": row.hospital,
                "lab_unit": row.lab_unit,
                "state": row.state,
                "consensus_status": row.consensus_status,
                "consensus_method": row.consensus_method,
                "final_impression": row.final_impression,
                "has_review": "yes" if has_review else "no",
                "resident_grade": grades.get("resident", {}).get("impression"),
                "resident_comment": grades.get("resident", {}).get("comment"),
                "resident_features_json": _serialize_features_json(
                    grades.get("resident", {}).get("selected_features")
                ),
                "resident2_grade": grades.get("resident2", {}).get("impression"),
                "resident2_comment": grades.get("resident2", {}).get("comment"),
                "resident2_features_json": _serialize_features_json(
                    grades.get("resident2", {}).get("selected_features")
                ),
                "arbitrator_grade": grades.get("arbitrator", {}).get("impression"),
                "arbitrator_comment": grades.get("arbitrator", {}).get("comment"),
                "arbitrator_features_json": _serialize_features_json(
                    grades.get("arbitrator", {}).get("selected_features")
                ),
                "review_grade": grades.get("review", {}).get("impression"),
                "review_comment": grades.get("review", {}).get("comment"),
                "review_features_json": _serialize_features_json(
                    grades.get("review", {}).get("selected_features")
                ),
                "ai_grade": ai_grade.get("impression"),
                "ai_model_name": ai_grade.get("ai_model_name"),
                "ai_model_version": ai_grade.get("ai_model_version"),
                "ai_probability": ai_grade.get("ai_probability"),
                "ai_review_statuses": "; ".join(ai_grade.get("ai_review_statuses") or []),
                "ai_review_comments": "; ".join(ai_grade.get("ai_review_comments") or []),
                "image_uuid": image_uuid,
                "image_filename": renamed_filename,
                "image_path": file_path,
            }
        )
    return data


def _fetch_rows_by_task_ids(task_ids: Sequence[int], disease_id: Optional[int] = None) -> List[ExportTaskRow]:
    """Fetch tasks by explicit ids for dataset export."""
    with get_db_session() as db:
        if not task_ids:
            return []

        # Use provided disease_id to pick MV columns; dataset is disease-specific
        if disease_id is None:
            disease_id = (
                db.query(GradingTask.disease_id).filter(GradingTask.id.in_(task_ids)).limit(1).scalar()
            )

        disease_key = _resolve_disease_key(db, disease_id)
        mv_detail_col = f"{disease_key}_grading_details_json"
        mv_ai_count_col = f"{disease_key}_ai_grading_count"
        mv_consensus_col = f"{disease_key}_consensus_status"

        params: Dict[str, Any] = {"task_ids": list(task_ids)}

        base_query = f"""
            FROM mvw_image_listing_all v
            JOIN grading_tasks gt ON (
                (v.direct_image_upload_id IS NOT NULL AND gt.direct_image_upload_id = v.direct_image_upload_id) OR
                (v.encounter_file_id IS NOT NULL AND gt.encounter_file_id = v.encounter_file_id)
            )
            LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
            LEFT JOIN hospitals h ON lu.hospital_id = h.id
            LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
            LEFT JOIN patient_encounters pe ON ef.patient_encounter_id = pe.id
            LEFT JOIN zip_files zf ON pe.zip_file_id = zf.id
            LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id
            LEFT JOIN consensus c ON gt.id = c.task_id
            LEFT JOIN disease_gradings dg ON c.final_disease_grading_id = dg.id
            WHERE gt.id = ANY(:task_ids)
        """

        data_sql = f"""
            SELECT
                gt.id AS task_id,
                gt.uuid AS task_uuid,
                gt.state AS task_state,
                lu.name AS lab_unit_name,
                h.name AS hospital_name,
                {mv_detail_col} AS grading_details_json,
                {mv_consensus_col} AS consensus_status,
                {mv_ai_count_col} AS ai_grading_count,
                c.id AS consensus_id,
                dg.impression AS final_impression,
                c.method AS consensus_method,
                gt.encounter_file_id,
                ef.uuid AS encounter_file_uuid,
                ef.filename AS encounter_filename,
                zf.upload_date AS encounter_upload_date,
                gt.direct_image_upload_id,
                diu.uuid AS direct_image_uuid,
                diu.filename AS direct_filename,
                diu.folder_rel AS direct_folder_rel
            {base_query}
        """

        rows = db.execute(text(data_sql), params).fetchall()
        task_ids_result = [row.task_id for row in rows]

        ai_review_comments: Dict[int, List[str]] = {}
        ai_review_statuses: Dict[int, List[str]] = {}
        if task_ids_result:
            ai_review_rows = (
                db.query(Grade.task_id, Grade.ai_review_comment, Grade.ai_review_status)
                .filter(Grade.role_slot == "ai", Grade.task_id.in_(task_ids_result))
                .filter(or_(Grade.ai_review_comment.isnot(None), Grade.ai_review_status.isnot(None)))
                .all()
            )
            for task_id, comment, status in ai_review_rows:
                if comment:
                    ai_review_comments.setdefault(task_id, []).append(comment)
                if status:
                    ai_review_statuses.setdefault(task_id, []).append(status)

        disease_map = {d.id: d.name for d in db.query(Disease).all()}
        disease_name = disease_map.get(disease_id, "")

        results: List[ExportTaskRow] = []
        for row in rows:
            results.append(
                ExportTaskRow(
                    task_id=row.task_id,
                    task_uuid=str(row.task_uuid),
                    disease=disease_name,
                    lab_unit=row.lab_unit_name,
                    hospital=row.hospital_name,
                    state=row.task_state,
                    consensus_status=row.consensus_status,
                    consensus_method=row.consensus_method,
                    final_impression=row.final_impression,
                    grading_details_json=row.grading_details_json or "[]",
                    ai_review_comments=ai_review_comments.get(row.task_id, []),
                    ai_review_statuses=ai_review_statuses.get(row.task_id, []),
                    encounter_file_id=row.encounter_file_id,
                    encounter_file_uuid=row.encounter_file_uuid,
                    encounter_filename=row.encounter_filename,
                    encounter_upload_date=row.encounter_upload_date,
                    direct_image_upload_id=row.direct_image_upload_id,
                    direct_image_uuid=row.direct_image_uuid,
                    direct_filename=row.direct_filename,
                    direct_folder_rel=row.direct_folder_rel,
                )
            )
        return results


def _load_encounter_paths(encounter_ids: Sequence[int]) -> Dict[int, tuple[Path, str]]:
    mapping: Dict[int, tuple[Path, str]] = {}
    if not encounter_ids:
        return mapping
    with get_db_session() as db:
        rows = (
            db.query(EncounterFile.id, EncounterFile.filename, ZipUpload.upload_date)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipUpload, PatientEncounters.zip_file_id == ZipUpload.id)
            .filter(EncounterFile.id.in_(encounter_ids))
            .all()
        )
        for enc_id, filename, upload_date in rows:
            if not filename or not upload_date:
                continue
            date_str = upload_date.strftime("%Y_%m_%d")
            path = (IMAGE_DIR / date_str / filename).resolve()
            mapping[enc_id] = (path, Path(filename).suffix.lower() or ".jpg")
    return mapping


def _load_direct_paths(direct_ids: Sequence[int]) -> Dict[int, tuple[Path, str]]:
    mapping: Dict[int, tuple[Path, str]] = {}
    if not direct_ids:
        return mapping
    with get_db_session() as db:
        rows = (
            db.query(DirectImageUpload.id, DirectImageUpload.folder_rel, DirectImageUpload.filename, DirectImageUpload.edited_filename)
            .filter(DirectImageUpload.id.in_(direct_ids))
            .all()
        )
        for img_id, folder_rel, filename, edited_filename in rows:
            try:
                # Prioritize edited version if it exists
                if edited_filename:
                    path = (DIRECT_UPLOAD_DIR / folder_rel / "edited" / edited_filename).resolve()
                    ext = Path(edited_filename).suffix.lower() or ".jpg"
                else:
                    path = (DIRECT_UPLOAD_DIR / folder_rel / filename).resolve()
                    ext = Path(filename).suffix.lower() or ".jpg"
                mapping[img_id] = (path, ext)
            except Exception:
                continue
    return mapping


def _write_excel(
    rows: List[Dict[str, Any]],
    filters: Dict[str, Any],
    export_dir: Path,
    drop_ai_columns: bool = False,
) -> Path:
    # Hide internal paths from the spreadsheet
    excluded_keys = {"image_path"}
    if drop_ai_columns:
        excluded_keys.update(
            {
                "ai_grade",
                "ai_model_name",
                "ai_model_version",
                "ai_probability",
                "ai_review_statuses",
                "ai_review_comments",
            }
        )
    sanitized_rows = [{k: v for k, v in row.items() if k not in excluded_keys} for row in rows]
    df = pd.DataFrame(sanitized_rows)
    filters_df = pd.DataFrame(
        [
            {
                "filter": k,
                "value": ", ".join([str(item) for item in v]) if isinstance(v, list) else v,
            }
            for k, v in filters.items()
        ]
    )
    excel_path = export_dir / "data.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Discrepancy Tasks", index=False)
        filters_df.to_excel(writer, sheet_name="Filters Applied", index=False)

    # Also provide .xls naming for compatibility (same content, xlsx format)
    xls_path = export_dir / "data.xls"
    xls_path.write_bytes(excel_path.read_bytes())

    # Write filters.txt
    filters_txt = export_dir / "filters.txt"
    try:
        filters_txt.write_text(
            "\n".join(
                f"{k}: {', '.join([str(item) for item in v]) if isinstance(v, list) else v}"
                for k, v in filters.items()
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    # Write metadata.txt (based on disease + final_impression columns in excel)
    try:
        metadata_lines: List[str] = []
        if "disease" in df.columns and "final_impression" in df.columns:
            working = df.assign(
                disease=df["disease"].fillna("Unknown").astype(str),
                final_impression=df["final_impression"].fillna("Unlabeled").astype(str),
            )
            for disease_val in sorted(working["disease"].unique()):
                disease_rows = working[working["disease"] == disease_val]
                metadata_lines.append(f"Number of Images: {int(disease_rows.shape[0])}")
                metadata_lines.append(f"Disease: {disease_val}")
                metadata_lines.append("Grades:")
                grade_counts = disease_rows["final_impression"].value_counts(dropna=False)
                for grade_name, count in grade_counts.items():
                    metadata_lines.append(f"- {grade_name}: {int(count)}")
                metadata_lines.append("")
        else:
            # Fallback to overall summary when columns are missing
            total_images = len(df.index)
            metadata_lines.append(f"Number of Images: {total_images}")
            metadata_lines.append("Disease: ")
            metadata_lines.append("Grades:")
            metadata_lines.append("- final_impression column not found")

        metadata_path = export_dir / "metadata.txt"
        metadata_path.write_text("\n".join(metadata_lines).strip() + "\n", encoding="utf-8")
    except Exception:
        pass

    return excel_path


def _write_grading_scheme(disease_id: Optional[int], export_dir: Path) -> None:
    if not disease_id:
        return
    with get_db_session() as db:
        disease = db.get(Disease, disease_id)
        disease_name = disease.name if disease else None
        gradings = (
            db.query(DiseaseGrading.impression, DiseaseGrading.guidelines)
            .filter(DiseaseGrading.disease_id == disease_id, DiseaseGrading.is_active.is_(True))
            .order_by(DiseaseGrading.display_order)
            .all()
        )
        grading_rows = [(row.impression, row.guidelines) for row in gradings]
    if not grading_rows:
        return

    lines: List[str] = []
    lines.append("Grading Scheme")
    if disease_name:
        lines.append(f"Disease: {disease_name}")
    lines.append("")
    def _strip_html(text: str) -> str:
        clean = text or ""
        clean = re.sub(r"(?i)<br\s*/?>", "\n", clean)
        clean = re.sub(r"(?i)</p\s*>", "\n", clean)
        clean = re.sub(r"(?i)<p[^>]*>", "", clean)
        clean = re.sub(r"(?i)<li[^>]*>", "\n- ", clean)
        clean = re.sub(r"(?i)</li>", "", clean)
        clean = re.sub(r"(?i)</(ul|ol)\s*>", "\n", clean)
        clean = re.sub(r"(?i)<(ul|ol)[^>]*>", "", clean)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = html.unescape(clean)
        lines = [re.sub(r"\s+", " ", line).strip() for line in clean.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    for idx, (impression_val, guidelines_val) in enumerate(grading_rows, start=1):
        impression = impression_val or "Unlabeled"
        guidelines = _strip_html(guidelines_val or "")
        lines.append(f"{idx}. {impression}")
        if guidelines:
            lines.append("   Instructions:")
            for gline in guidelines.splitlines():
                lines.append(f"   {gline}")
        lines.append("")

    scheme_path = export_dir / "Grading_Scheme.txt"
    try:
        scheme_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    except Exception:
        pass


def _write_zips(rows: List[Dict[str, Any]], export_dir: Path) -> tuple[List[Path], List[str]]:
    zip_paths: List[Path] = []
    warnings: List[str] = []

    current_zip_index = 1
    current_zip_path = export_dir / f"{current_zip_index}.zip"
    current_zip = ZipFile(current_zip_path, "w", compression=ZIP_DEFLATED)
    current_zip_bytes = 0
    current_zip_count = 0

    def rotate_zip():
        nonlocal current_zip_index, current_zip_path, current_zip, current_zip_bytes, current_zip_count
        current_zip.close()
        zip_paths.append(current_zip_path)
        current_zip_index += 1
        current_zip_path = export_dir / f"{current_zip_index}.zip"
        current_zip = ZipFile(current_zip_path, "w", compression=ZIP_DEFLATED)
        current_zip_bytes = 0
        current_zip_count = 0

    for row in rows:
        image_path: Optional[Path] = row.get("image_path")
        image_filename: Optional[str] = row.get("image_filename")
        if not image_path or not image_filename:
            warnings.append(f"Task {row.get('task_id')}: missing image path")
            continue
        if not image_path.exists():
            warnings.append(f"Task {row.get('task_id')}: image file not found on disk")
            continue

        file_size = image_path.stat().st_size
        if file_size > MAX_BYTES_PER_ZIP:
            warnings.append(f"Task {row.get('task_id')}: image size exceeds 200MB cap, skipped")
            continue
        if current_zip_count >= MAX_ROWS_PER_ZIP or (current_zip_bytes + file_size) > MAX_BYTES_PER_ZIP:
            rotate_zip()

        current_zip.write(image_path, arcname=image_filename)
        current_zip_bytes += file_size
        current_zip_count += 1

    current_zip.close()
    zip_paths.append(current_zip_path)

    zip_paths = sorted(set(zip_paths))
    return zip_paths, warnings
