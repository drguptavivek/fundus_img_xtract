"""Utilities to fetch the next review task respecting discrepancy filters and ordering."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from utils.discrepancy_filters import build_discrepancy_filter_query


def get_next_review_tasks(
    db: Session,
    *,
    current_task_id: int,
    disease_id: int,
    lab_unit_ids: List[int],
    project_id: Optional[int] = None,
    lab_unit_id: Optional[int] = None,
    has_consensus: Optional[str] = None,
    consensus_method: Optional[str] = None,
    has_review: Optional[str] = None,
    has_regrade: Optional[str] = None,
    has_arbitrator: Optional[str] = None,
    has_ai_grade: Optional[str] = None,
    has_human_review: Optional[str] = None,
    ai_model_id: Optional[int] = None,
    final_grade_basis: Optional[str] = None,
    ai_grades: Optional[List[str]] = None,
    ai_review_statuses: Optional[List[str]] = None,
    resident_grades: Optional[List[str]] = None,
    resident2_grades: Optional[List[str]] = None,
    arbitrator_grades: Optional[List[str]] = None,
    regrade_grades: Optional[List[str]] = None,
    review_grades: Optional[List[str]] = None,
    final_grades: Optional[List[str]] = None,
    project_capability_user_id: Optional[int] = None,
    project_capability_role_names: Optional[List[str]] = None,
    allow_classical_capability: bool = False,
    ordered_task_ids: Optional[List[int]] = None,
    limit: int = 50,
) -> Dict[str, Optional[int]]:
    """Return the next and next-after task ids in the discrepancy order for the given filters."""
    if ordered_task_ids:
        try:
            current_index = ordered_task_ids.index(current_task_id)
        except ValueError:
            return {"next_task_id": None, "next_after_task_id": None}

        ordered_ids = ordered_task_ids[current_index + 1 : current_index + 3]
        return {
            "next_task_id": ordered_ids[0] if ordered_ids else None,
            "next_after_task_id": ordered_ids[1] if len(ordered_ids) > 1 else None,
        }

    filters: Dict[str, Any] = {
        "disease_id": disease_id,
        "project_id": project_id,
        "lab_unit_id": lab_unit_id,
        "allowed_lab_units": lab_unit_ids,
        "has_consensus": has_consensus,
        "consensus_method": consensus_method,
        "has_review": has_review,
        "has_regrade": has_regrade,
        "has_arbitrator": has_arbitrator,
        "has_ai_grade": has_ai_grade,
        "has_human_review": has_human_review,
        "final_grade_basis": final_grade_basis,
        "ai_model_id": [ai_model_id] if ai_model_id else [],
        "ai_grade": ai_grades or [],
        "ai_review_status": ai_review_statuses or [],
        "resident_grade": resident_grades or [],
        "resident2_grade": resident2_grades or [],
        "arbitrator_grade": arbitrator_grades or [],
        "regrade_grade": regrade_grades or [],
        "review_grade": review_grades or [],
        "final_grade": final_grades or [],
        "project_capability_user_id": project_capability_user_id,
        "project_capability_role_names": project_capability_role_names or [],
        "allow_classical_capability": allow_classical_capability,
        "task_ids": ordered_task_ids or [],
    }

    mv_name, where_sql, params, _selected_ai_model_id = build_discrepancy_filter_query(db, filters)
    if not mv_name:
        return {"next_task_id": None, "next_after_task_id": None}

    base_query = f"""
        SELECT v.task_id
        FROM {mv_name} v
        WHERE {where_sql}
          AND v.task_id < :current_task_id
        ORDER BY v.task_id DESC
        LIMIT :limit
    """
    params["current_task_id"] = current_task_id
    params["limit"] = min(limit, 2)

    rows = db.execute(text(base_query), params).fetchall()
    ordered_ids = [row.task_id for row in rows]

    next_id = ordered_ids[0] if ordered_ids else None
    next_after_id = ordered_ids[1] if len(ordered_ids) > 1 else None

    return {"next_task_id": next_id, "next_after_task_id": next_after_id}
