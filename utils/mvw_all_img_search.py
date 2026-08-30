from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import or_, text
from sqlalchemy.orm import Session
import logging
from time import perf_counter

from models import Disease
from utils.final_grade_basis import normalize_final_grade_basis, sql_json_final_grade_expression
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)


@dataclass
class MVImageFilters:
    disease_id: int
    allowed_lab_units: List[int]
    lab_unit_id: Optional[int] = None
    resident_grades: List[str] = None
    resident2_grades: List[str] = None
    arbitrator_grades: List[str] = None
    review_grades: List[str] = None
    final_grades: List[str] = None
    has_ai_grade: Optional[str] = None
    has_review: Optional[str] = None
    has_consensus: Optional[str] = None
    final_grade_basis: Optional[str] = None
    ai_model_ids: List[str] = None
    ai_grades: List[str] = None
    ai_review_statuses: List[str] = None
    image_uuid: Optional[str] = None
    upload_after: Optional[date] = None
    upload_before: Optional[date] = None
    encounter_after: Optional[date] = None
    encounter_before: Optional[date] = None
    # The lab-unit list is only a transport narrowing hint.  Authorization
    # must be expressed as the exact task identities selected by
    # ``authz.behaviors.clinical_rows``; otherwise a project grant can expose
    # another project's task in the same Lab Unit.
    authorized_task_ids: Optional[List[int]] = None

    def normalise(self) -> None:
        """Ensure list fields are at least empty lists."""
        self.authorized_task_ids = [int(task_id) for task_id in (self.authorized_task_ids or [])]
        self.resident_grades = self.resident_grades or []
        self.resident2_grades = self.resident2_grades or []
        self.arbitrator_grades = self.arbitrator_grades or []
        self.review_grades = self.review_grades or []
        self.final_grades = self.final_grades or []
        self.final_grade_basis = normalize_final_grade_basis(self.final_grade_basis)
        self.ai_model_ids = self.ai_model_ids or []
        self.ai_grades = self.ai_grades or []
        self.ai_review_statuses = self.ai_review_statuses or []


@dataclass
class MVImageRow:
    task_id: int
    task_uuid: Optional[str]
    lab_unit_name: Optional[str]
    hospital_name: Optional[str]
    encounter_file_uuid: Optional[str]
    direct_image_uuid: Optional[str]
    grading_details_json: str
    consensus_status: Optional[str]
    ai_grading_count: int
    consensus_id: Optional[int]
    final_impression: Optional[str]
    consensus_method: Optional[str]
    upload_date: Optional[date]
    capture_date: Optional[date]


def _resolve_disease_key(db: Session, disease_id: int) -> str:
    """Map disease to mvw_image_listing_all column prefix."""
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


def build_where_clause(db: Session, filters: MVImageFilters) -> Tuple[str, Dict[str, Any]]:
    """Build SQL WHERE clause and params for MV-backed image search."""
    filters.normalise()
    disease_key = _resolve_disease_key(db, filters.disease_id)
    mv_detail_col = f"{disease_key}_grading_details_json"
    mv_ai_count_col = f"{disease_key}_ai_grading_count"
    mv_consensus_col = f"{disease_key}_consensus_status"
    final_grade_expr = sql_json_final_grade_expression(filters.final_grade_basis, mv_detail_col)

    where_clauses: List[str] = [
        "gt.disease_id = :disease_id",
        "gt.lab_unit_id = ANY(:allowed_lab_units)",
        # Do not replace this with a Lab Unit predicate.  Tasks from multiple
        # projects may share a Lab Unit, and project authorization is attached
        # to the task's maintained project lineage.
        "gt.id = ANY(:authorized_task_ids)",
    ]
    params: Dict[str, Any] = {
        "disease_id": filters.disease_id,
        "allowed_lab_units": list(filters.allowed_lab_units),
        "authorized_task_ids": list(filters.authorized_task_ids),
    }

    if filters.lab_unit_id and filters.lab_unit_id in filters.allowed_lab_units:
        where_clauses.append("gt.lab_unit_id = :lab_unit_id")
        params["lab_unit_id"] = filters.lab_unit_id

    if filters.has_consensus == "has_consensus":
        where_clauses.append("c.id IS NOT NULL")
    elif filters.has_consensus == "no":
        where_clauses.append("c.id IS NULL")

    if filters.has_review == "yes":
        where_clauses.append(
            f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
        )
        if filters.review_grades:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                "WHERE elem->>'role_slot' = 'review' AND elem->>'grade_name' = ANY(:review_grades))"
            )
            params["review_grades"] = filters.review_grades
    elif filters.has_review == "no":
        where_clauses.append(
            f"NOT EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
        )

    if filters.has_ai_grade == "yes":
        where_clauses.append(f"{mv_ai_count_col} > 0")
    elif filters.has_ai_grade == "no":
        where_clauses.append(f"{mv_ai_count_col} = 0")

    role_grade_filters = [
        ("resident", filters.resident_grades),
        ("resident2", filters.resident2_grades),
        ("arbitrator", filters.arbitrator_grades),
    ]
    for role, impressions in role_grade_filters:
        if impressions:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                "WHERE elem->>'role_slot' = :role_slot_"
                + role
                + " AND elem->>'grade_name' = ANY(:grade_names_"
                + role
                + "))"
            )
            params[f"role_slot_{role}"] = role
            params[f"grade_names_{role}"] = impressions

    if filters.ai_model_ids:
        selected_ai_model_id = next((mid for mid in filters.ai_model_ids if mid), None)
        if selected_ai_model_id:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                "WHERE elem->>'role_slot' = 'ai' AND (elem->>'ai_model_id')::int = :ai_model_id)"
            )
            params["ai_model_id"] = int(selected_ai_model_id)

    if filters.ai_grades:
        where_clauses.append(
            f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
            "WHERE elem->>'role_slot' = 'ai' AND elem->>'grade_name' = ANY(:ai_grade_names))"
        )
        params["ai_grade_names"] = filters.ai_grades

    if filters.ai_review_statuses:
        where_clauses.append(
            "EXISTS (SELECT 1 FROM grades g WHERE g.task_id = gt.id AND g.role_slot = 'ai' "
            "AND g.ai_review_status = ANY(:ai_review_statuses))"
        )
        params["ai_review_statuses"] = filters.ai_review_statuses

    if filters.final_grades:
        where_clauses.append(f"{final_grade_expr} = ANY(:final_grades)")
        params["final_grades"] = filters.final_grades

    if filters.image_uuid:
        where_clauses.append(
            "(ef.uuid = :image_uuid OR diu.uuid = :image_uuid)"
        )
        params["image_uuid"] = filters.image_uuid

    if filters.upload_after:
        where_clauses.append("(COALESCE(diu.created_at::date, zf.upload_date) >= :upload_after)")
        params["upload_after"] = filters.upload_after
    if filters.upload_before:
        where_clauses.append("(COALESCE(diu.created_at::date, zf.upload_date) <= :upload_before)")
        params["upload_before"] = filters.upload_before

    if filters.encounter_after:
        where_clauses.append("(pe.capture_date_dt >= :encounter_after)")
        params["encounter_after"] = filters.encounter_after
    if filters.encounter_before:
        where_clauses.append("(pe.capture_date_dt <= :encounter_before)")
        params["encounter_before"] = filters.encounter_before

    where_sql = " AND ".join(where_clauses)
    return where_sql, params


def search_mvw_images(
    db: Session,
    filters: MVImageFilters,
    *,
    per_page: int,
    offset: int,
) -> Tuple[List[MVImageRow], int]:
    """Execute the MV-backed image search with paging."""
    start_time = perf_counter()
    where_sql, params = build_where_clause(db, filters)

    disease_key = _resolve_disease_key(db, filters.disease_id)
    mv_detail_col = f"{disease_key}_grading_details_json"
    mv_ai_count_col = f"{disease_key}_ai_grading_count"
    mv_consensus_col = f"{disease_key}_consensus_status"
    final_grade_expr = sql_json_final_grade_expression(filters.final_grade_basis, mv_detail_col)

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

    total_count = db.execute(text(f"SELECT COUNT(*) {base_query}"), params).scalar() or 0

    params.update({"limit": per_page, "offset": offset})
    data_sql = f"""
        SELECT
            gt.id AS task_id,
            gt.uuid AS task_uuid,
            lu.name AS lab_unit_name,
            h.name AS hospital_name,
            ef.uuid AS encounter_file_uuid,
            diu.uuid AS direct_image_uuid,
            {mv_detail_col} AS grading_details_json,
            {mv_consensus_col} AS consensus_status,
            {mv_ai_count_col} AS ai_grading_count,
            c.id AS consensus_id,
            {final_grade_expr} AS final_impression,
            c.method AS consensus_method,
            COALESCE(diu.created_at::date, zf.upload_date) AS upload_date,
            pe.capture_date_dt AS capture_date
        {base_query}
        ORDER BY gt.id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(data_sql), params).fetchall()

    results: List[MVImageRow] = []
    for row in rows:
        results.append(
            MVImageRow(
                task_id=row.task_id,
                task_uuid=str(row.task_uuid) if row.task_uuid else None,
                lab_unit_name=row.lab_unit_name,
                hospital_name=row.hospital_name,
                encounter_file_uuid=row.encounter_file_uuid,
                direct_image_uuid=row.direct_image_uuid,
                grading_details_json=row.grading_details_json or "[]",
                consensus_status=row.consensus_status,
                ai_grading_count=row.ai_grading_count or 0,
                consensus_id=row.consensus_id,
                final_impression=row.final_impression,
                consensus_method=row.consensus_method,
                upload_date=row.upload_date,
                capture_date=row.capture_date,
            )
        )
    
    duration = perf_counter() - start_time
    logger.info(
        "MVW Search completed - Count: %s, Time: %.3fs",
        sanitize_log_value(total_count),
        duration
    )

    return results, total_count
