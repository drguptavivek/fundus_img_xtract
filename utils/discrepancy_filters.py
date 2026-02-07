from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text

from models import DiseaseGrading
from utils.mvw_image_listing_v2 import get_mv_name_for_disease


def build_discrepancy_filter_query(
    db,
    filters: Dict[str, Any],
) -> Tuple[str, str, Dict[str, Any], Optional[int]]:
    disease_id = filters.get("disease_id")
    lab_unit_id = filters.get("lab_unit_id")
    resident_grades = filters.get("resident_grade", [])
    resident2_grades = filters.get("resident2_grade", [])
    arbitrator_grades = filters.get("arbitrator_grade", [])
    final_grades = filters.get("final_grade", [])
    has_ai_grade = filters.get("has_ai_grade")
    has_review = filters.get("has_review")
    has_arbitrator = filters.get("has_arbitrator")
    review_grades = filters.get("review_grade", [])
    has_consensus = filters.get("has_consensus")
    consensus_method = filters.get("consensus_method")
    resident_compare = filters.get("resident_compare")
    if has_consensus == "no":
        consensus_method = None
        final_grades = []
        has_arbitrator = None
        arbitrator_grades = []
        has_review = None
        review_grades = []

    ai_model_ids = filters.get("ai_model_id", [])
    ai_grades = filters.get("ai_grade", [])
    ai_review_statuses = filters.get("ai_review_status", [])
    allowed_lab_units: List[int] = filters.get("allowed_lab_units", [])
    if not allowed_lab_units:
        return "", "", {}, None

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

    mv_name = get_mv_name_for_disease(db, disease_id)

    where_clauses = [
        "v.disease_id = :disease_id",
        "v.task_lab_unit_id = ANY(:allowed_lab_units)",
    ]
    params: Dict[str, Any] = {"disease_id": disease_id, "allowed_lab_units": allowed_lab_units}

    if lab_unit_id and lab_unit_id in allowed_lab_units:
        where_clauses.append("v.task_lab_unit_id = :lab_unit_id")
        params["lab_unit_id"] = lab_unit_id

    require_final_grade = bool(filters.get("require_final_grade"))
    if has_consensus == "has_consensus":
        where_clauses.append("v.has_consensus = TRUE")
        if require_final_grade:
            where_clauses.append("v.final_grade_name IS NOT NULL")
    elif has_consensus == "no":
        where_clauses.append("v.has_consensus = FALSE")

    if consensus_method in {"match", "adjudication", "task_review", "regrade"}:
        where_clauses.append("v.consensus_type = :consensus_method")
        params["consensus_method"] = consensus_method

    if has_review == "yes":
        where_clauses.append("v.has_review = TRUE")
        valid_review_grades = [g for g in review_grades if g]
        if valid_review_grades:
            where_clauses.append("v.review_grade_name = ANY(:review_grades)")
            params["review_grades"] = valid_review_grades
    elif has_review == "no":
        where_clauses.append("v.has_review = FALSE")

    if has_arbitrator == "yes":
        where_clauses.append("v.has_arbitrator = TRUE")
    elif has_arbitrator == "no":
        where_clauses.append("v.has_arbitrator = FALSE")

    if has_ai_grade == "yes":
        where_clauses.append("v.has_ai = TRUE")
    elif has_ai_grade == "no":
        where_clauses.append("v.has_ai = FALSE")
    else:
        ai_model_ids = []
        ai_grades = []
        ai_review_statuses = []

    role_grade_filters = [
        ("resident", resident_grades, "resident_grade_name"),
        ("resident2", resident2_grades, "resident2_grade_name"),
        ("arbitrator", arbitrator_grades, "arbitrator_grade_name"),
    ]
    for role, impressions, column in role_grade_filters:
        if impressions:
            valid = [g for g in impressions if g]
            if valid:
                where_clauses.append(f"v.{column} = ANY(:grade_names_{role})")
                params[f"grade_names_{role}"] = valid

    if resident_compare in {"match", "mismatch"}:
        where_clauses.append("v.resident_vs_resident2 = :resident_compare")
        params["resident_compare"] = resident_compare

    selected_ai_model_id: Optional[int] = None
    if ai_model_ids:
        cleaned_models = [mid for mid in ai_model_ids if mid]
        if cleaned_models:
            selected_ai_model_id = int(cleaned_models[0])
            ai_model_ids = [str(selected_ai_model_id)]
        else:
            ai_model_ids = []

    if selected_ai_model_id is not None:
        where_clauses.append("v.ai_models_json ? :ai_model_key")
        params["ai_model_key"] = str(selected_ai_model_id)

    if ai_grades:
        valid_ai_grades = [g for g in ai_grades if g]
        if valid_ai_grades:
            if selected_ai_model_id is not None:
                where_clauses.append(
                    "(v.ai_models_json -> :ai_model_key) ->> 'ai_grade_name' = ANY(:ai_grade_names)"
                )
            else:
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM jsonb_each(v.ai_models_json) kv "
                    "WHERE kv.value->>'ai_grade_name' = ANY(:ai_grade_names))"
                )
            params["ai_grade_names"] = valid_ai_grades

    if ai_review_statuses:
        valid_statuses = [s for s in ai_review_statuses if s]
        if valid_statuses:
            if selected_ai_model_id is not None:
                where_clauses.append(
                    "(v.ai_models_json -> :ai_model_key) ->> 'ai_review_status' = ANY(:ai_review_statuses)"
                )
            else:
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM jsonb_each(v.ai_models_json) kv "
                    "WHERE kv.value->>'ai_review_status' = ANY(:ai_review_statuses))"
                )
            params["ai_review_statuses"] = valid_statuses

    if final_grades:
        valid_final_grades = [g for g in final_grades if g]
        if valid_final_grades:
            where_clauses.append("v.final_grade_name = ANY(:final_grades)")
            params["final_grades"] = valid_final_grades

    excluded_dataset_ids = filters.get("excluded_dataset_ids", [])
    if excluded_dataset_ids:
        where_clauses.append(
            "NOT EXISTS ("
            "SELECT 1 FROM curated_dataset_items cdi "
            "WHERE cdi.task_id = v.task_id "
            "AND cdi.dataset_id = ANY(:excluded_dataset_ids) "
            "AND cdi.include_in_export = true"
            ")"
        )
        params["excluded_dataset_ids"] = excluded_dataset_ids

    where_sql = " AND ".join(where_clauses)
    return mv_name, where_sql, params, selected_ai_model_id
