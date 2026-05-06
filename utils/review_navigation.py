"""Utilities to fetch the next review task respecting discrepancy filters and ordering."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.discrepancy_filters import AI_REVIEW_STATUS_MISSING


def get_next_review_tasks(
    db: Session,
    *,
    current_task_id: int,
    disease_id: int,
    lab_unit_ids: List[int],
    lab_unit_id: Optional[int] = None,
    has_consensus: Optional[str] = None,
    has_review: Optional[str] = None,
    has_ai_grade: Optional[str] = None,
    ai_model_id: Optional[int] = None,
    ai_grades: Optional[List[str]] = None,
    ai_review_statuses: Optional[List[str]] = None,
    resident_grades: Optional[List[str]] = None,
    resident2_grades: Optional[List[str]] = None,
    arbitrator_grades: Optional[List[str]] = None,
    final_grades: Optional[List[str]] = None,
    limit: int = 50,
) -> Dict[str, Optional[int]]:
    """Return the next and next-after task ids in the discrepancy order for the given filters."""
    disease_key = _resolve_disease_key(db, disease_id)
    mv_detail_col = f"{disease_key}_grading_details_json"
    mv_ai_count_col = f"{disease_key}_ai_grading_count"
    mv_consensus_col = f"{disease_key}_consensus_status"

    where_clauses: List[str] = [
        "gt.disease_id = :disease_id",
        "gt.lab_unit_id = ANY(:allowed_lab_units)",
    ]
    params: Dict[str, Any] = {
        "disease_id": disease_id,
        "allowed_lab_units": lab_unit_ids,
    }

    if lab_unit_id and lab_unit_id in lab_unit_ids:
        where_clauses.append("gt.lab_unit_id = :lab_unit_id")
        params["lab_unit_id"] = lab_unit_id

    if has_consensus == "has_consensus":
        where_clauses.append("c.id IS NOT NULL")
    elif has_consensus == "no":
        where_clauses.append("c.id IS NULL")

    if has_review == "yes":
        where_clauses.append(
            f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
        )
    elif has_review == "no":
        where_clauses.append(
            f"NOT EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
        )

    if has_ai_grade == "yes":
        where_clauses.append(f"{mv_ai_count_col} > 0")
    elif has_ai_grade == "no":
        where_clauses.append(f"{mv_ai_count_col} = 0")

    if ai_model_id:
        where_clauses.append(
            f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
            "WHERE elem->>'role_slot' = 'ai' AND (elem->>'ai_model_id')::int = :ai_model_id)"
        )
        params["ai_model_id"] = ai_model_id

    if ai_grades:
        valid_ai_grades = [g for g in ai_grades if g]
        if valid_ai_grades:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                "WHERE elem->>'role_slot' = 'ai' AND elem->>'grade_name' = ANY(:ai_grade_names))"
            )
            params["ai_grade_names"] = valid_ai_grades

    if ai_review_statuses:
        valid_statuses = [
            s for s in ai_review_statuses if s and s != AI_REVIEW_STATUS_MISSING
        ]
        include_missing_status = AI_REVIEW_STATUS_MISSING in ai_review_statuses
        if valid_statuses or include_missing_status:
            status_clauses = []
            if valid_statuses:
                status_clauses.append(
                    f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                    "WHERE elem->>'role_slot' = 'ai' AND elem->>'ai_review_status' = ANY(:ai_review_statuses))"
                )
                params["ai_review_statuses"] = valid_statuses
            if include_missing_status:
                status_clauses.append(
                    f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                    "WHERE elem->>'role_slot' = 'ai' "
                    "AND COALESCE(NULLIF(elem->>'ai_review_status', ''), '') = '')"
                )
            where_clauses.append(f"({' OR '.join(status_clauses)})")

    for role, impressions in (
        ("resident", resident_grades),
        ("resident2", resident2_grades),
        ("arbitrator", arbitrator_grades),
    ):
        if impressions:
            valid_impressions = [g for g in impressions if g]
            if valid_impressions:
                where_clauses.append(
                    f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                    "WHERE elem->>'role_slot' = :role_slot_"
                    + role
                    + " AND elem->>'grade_name' = ANY(:grade_names_"
                    + role
                    + "))"
                )
                params[f"role_slot_{role}"] = role
                params[f"grade_names_{role}"] = valid_impressions

    if final_grades:
        valid_final_grades = [g for g in final_grades if g]
        if valid_final_grades:
            where_clauses.append("dg.impression = ANY(:final_grades)")
            params["final_grades"] = valid_final_grades

    where_sql = " AND ".join(where_clauses)

    base_query = f"""
        SELECT gt.id AS task_id
        FROM mvw_image_listing_all v
        JOIN grading_tasks gt ON (
            (v.direct_image_upload_id IS NOT NULL AND gt.direct_image_upload_id = v.direct_image_upload_id) OR
            (v.encounter_file_id IS NOT NULL AND gt.encounter_file_id = v.encounter_file_id)
        )
        LEFT JOIN consensus c ON gt.id = c.task_id
        LEFT JOIN disease_gradings dg ON c.final_disease_grading_id = dg.id
        WHERE {where_sql}
        ORDER BY gt.id DESC
        LIMIT :limit
    """
    params["limit"] = limit

    rows = db.execute(text(base_query), params).fetchall()
    ordered_ids = [row.task_id for row in rows]

    next_id = None
    next_after_id = None
    if current_task_id in ordered_ids:
        idx = ordered_ids.index(current_task_id)
        if idx + 1 < len(ordered_ids):
            next_id = ordered_ids[idx + 1]
        if idx + 2 < len(ordered_ids):
            next_after_id = ordered_ids[idx + 2]

    return {"next_task_id": next_id, "next_after_task_id": next_after_id}


def _resolve_disease_key(db: Session, disease_id: int) -> str:
    """Map disease to mvw_image_listing_all column prefix."""
    from models import Disease

    disease = db.get(Disease, disease_id)
    if not disease:
        return "dr"
    name = (disease.name or "").lower()
    if "glaucoma" in name:
        return "glaucoma"
    if "amd" in name or "macular" in name:
        return "amd"
    return "dr"
