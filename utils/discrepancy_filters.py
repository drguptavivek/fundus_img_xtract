from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import text

from authz.project_roles import PROJECT_ASSIGNABLE_ROLES
from models import DiseaseGrading
from utils.final_grade_basis import (
    FINAL_GRADE_UNRESOLVED,
    basis_uses_unresolved,
    normalize_final_grade_basis,
    sql_final_grade_expression,
)
from utils.mvw_image_listing_v2 import get_mv_name_for_disease

AI_REVIEW_STATUS_MISSING = "missing"
PROJECT_CAPABILITY_ROLE_NAMES = set(PROJECT_ASSIGNABLE_ROLES)


def build_discrepancy_filter_query(
    db,
    filters: Dict[str, Any],
) -> Tuple[str, str, Dict[str, Any], Optional[int]]:
    disease_id = filters.get("disease_id")
    project_id = filters.get("project_id")
    lab_unit_id = filters.get("lab_unit_id")
    resident_grades = filters.get("resident_grade", [])
    resident2_grades = filters.get("resident2_grade", [])
    arbitrator_grades = filters.get("arbitrator_grade", [])
    regrade_grades = filters.get("regrade_grade", [])
    final_grades = filters.get("final_grade", [])
    final_grade_basis = normalize_final_grade_basis(filters.get("final_grade_basis"))
    has_ai_grade = filters.get("has_ai_grade")
    has_human_review = filters.get("has_human_review")
    review_status = {"yes": "any", "no": "unreviewed"}.get(
        has_human_review, has_human_review
    )
    has_review = filters.get("has_review")
    has_regrade = filters.get("has_regrade")
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
        has_regrade = None
        regrade_grades = []

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
        regrade_grades = [g for g in regrade_grades if g in valid_grade_impressions]
        allowed_final_grades = set(valid_grade_impressions)
        if basis_uses_unresolved(final_grade_basis):
            allowed_final_grades.add(FINAL_GRADE_UNRESOLVED)
        final_grades = [g for g in final_grades if g in allowed_final_grades]
        review_grades = [g for g in review_grades if g in valid_grade_impressions]
        ai_grades = [g for g in ai_grades if g in valid_grade_impressions]

    mv_name = get_mv_name_for_disease(db, disease_id)

    where_clauses = [
        "v.disease_id = :disease_id",
        "v.task_lab_unit_id = ANY(:allowed_lab_units)",
    ]
    params: Dict[str, Any] = {
        "disease_id": disease_id,
        "allowed_lab_units": allowed_lab_units,
        "final_grade_basis": final_grade_basis,
    }
    task_ids = [int(task_id) for task_id in filters.get("task_ids", []) if task_id]
    if task_ids:
        where_clauses.append("v.task_id = ANY(:task_ids)")
        params["task_ids"] = task_ids

    if project_id is not None:
        where_clauses.append(
            """EXISTS (
                SELECT 1
                FROM grading_tasks selected_project_task
                LEFT JOIN patient_encounters selected_task_encounter
                  ON selected_task_encounter.id = selected_project_task.patient_encounter_id
                LEFT JOIN encounter_set_images selected_task_set_image
                  ON selected_task_set_image.id = selected_project_task.encounter_set_image_id
                LEFT JOIN patient_encounters selected_set_image_encounter
                  ON selected_set_image_encounter.id = selected_task_set_image.patient_encounter_id
                LEFT JOIN encounter_files selected_task_image
                  ON selected_task_image.id = selected_project_task.encounter_file_id
                LEFT JOIN patient_encounters selected_task_image_encounter
                  ON selected_task_image_encounter.id = selected_task_image.patient_encounter_id
                LEFT JOIN direct_image_uploads selected_task_direct
                  ON selected_task_direct.id = selected_project_task.direct_image_upload_id
                WHERE selected_project_task.id = v.task_id
                  AND COALESCE(
                    selected_task_encounter.project_id,
                    selected_task_set_image.project_id,
                    selected_set_image_encounter.project_id,
                    selected_task_image.project_id,
                    selected_task_image_encounter.project_id,
                    selected_task_direct.project_id
                  ) = :project_id
            )"""
        )
        params["project_id"] = int(project_id)

    capability_role_names = [
        value
        for value in filters.get("project_capability_role_names", [])
        if value in PROJECT_CAPABILITY_ROLE_NAMES
    ]
    project_user_id = filters.get("project_capability_user_id")
    if not project_user_id:
        return "", "", {}, None

    authorization_sql = [
        """EXISTS (
              SELECT 1
              FROM user_roles actor_role_link
              JOIN roles actor_role ON actor_role.id = actor_role_link.role_id
              WHERE actor_role_link.user_id = :project_capability_user_id
                AND actor_role.name = 'admin'
            )"""
    ]
    if capability_role_names:
        # Project-wide access requires a project grant; Lab-scoped access is
        # valid only for the exact task Lab Unit. Missing lineage matches none.
        if filters.get("project_capability_require_project_scope"):
            scope_sql = "prg.scope_type = 'project'"
        else:
            scope_sql = """prg.scope_type = 'project'
                      OR (
                        prg.scope_type = 'lab_unit'
                        AND prg.lab_unit_id = project_task.lab_unit_id
                      )"""
        authorized_grant_ids = filters.get("project_capability_grant_ids")
        grant_constraint = (
            "AND prg.id = ANY(:project_capability_grant_ids)"
            if authorized_grant_ids is not None
            else "AND project_role.name = ANY(:project_capability_role_names)"
        )
        authorization_sql.append(
            """EXISTS (
                  SELECT 1
                  FROM project_role_grants prg
                  JOIN roles project_role ON project_role.id = prg.role_id
                  WHERE prg.user_id = :project_capability_user_id
                    AND prg.project_id = COALESCE(
                      task_encounter.project_id,
                      task_set_image.project_id,
                      set_image_encounter.project_id,
                      task_image.project_id,
                      task_image_encounter.project_id,
                      task_direct.project_id
                    )
                    AND prg.active = TRUE
                    {grant_constraint}
                    AND EXISTS (
                      SELECT 1
                      FROM project_lab_units active_project_lab
                      WHERE active_project_lab.project_id = prg.project_id
                        AND active_project_lab.lab_unit_id = project_task.lab_unit_id
                        AND active_project_lab.active = TRUE
                    )
                    AND ({scope_sql})
                )""".replace("{scope_sql}", scope_sql).replace(
                    "{grant_constraint}", grant_constraint
                )
        )
    project_authorization_sql = " OR ".join(authorization_sql)
    classical_authorization_sql = (
            """COALESCE(
                      task_encounter.project_id,
                      task_set_image.project_id,
                      set_image_encounter.project_id,
                      task_image.project_id,
                      task_image_encounter.project_id,
                      task_direct.project_id
                    ) IS NULL OR"""
            if filters.get("allow_classical_capability")
            else ""
        )
    where_clauses.append(
        f"""EXISTS (
                SELECT 1
                FROM grading_tasks project_task
                LEFT JOIN patient_encounters task_encounter
                  ON task_encounter.id = project_task.patient_encounter_id
                LEFT JOIN encounter_set_images task_set_image
                  ON task_set_image.id = project_task.encounter_set_image_id
                LEFT JOIN patient_encounters set_image_encounter
                  ON set_image_encounter.id = task_set_image.patient_encounter_id
                LEFT JOIN encounter_files task_image
                  ON task_image.id = project_task.encounter_file_id
                LEFT JOIN patient_encounters task_image_encounter
                  ON task_image_encounter.id = task_image.patient_encounter_id
                LEFT JOIN direct_image_uploads task_direct
                  ON task_direct.id = project_task.direct_image_upload_id
                WHERE project_task.id = v.task_id
                  AND (
                    {classical_authorization_sql} ({project_authorization_sql})
                  )
        )"""
    )
    params["project_capability_user_id"] = int(project_user_id)
    if capability_role_names:
        params["project_capability_role_names"] = capability_role_names
    if filters.get("project_capability_grant_ids") is not None:
        params["project_capability_grant_ids"] = list(
            filters.get("project_capability_grant_ids") or []
        )

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

    if has_regrade == "yes":
        where_clauses.append("v.has_regrade_adj = TRUE")
        valid_regrade_grades = [g for g in regrade_grades if g]
        if valid_regrade_grades:
            where_clauses.append("v.regrade_adj_grade_name = ANY(:regrade_grades)")
            params["regrade_grades"] = valid_regrade_grades
    elif has_regrade == "no":
        where_clauses.append("v.has_regrade_adj = FALSE")

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

    if review_status in {"unreviewed", "human", "ai", "both", "any"}:
        human_evidence = (
            "(v.has_review = TRUE OR "
            "COALESCE(NULLIF(BTRIM(v.review_comment), ''), '') <> '')"
        )
        if selected_ai_model_id is not None:
            selected_ai = "v.ai_models_json -> :ai_model_key"
            ai_evidence = (
                "(COALESCE(NULLIF((" + selected_ai + ")->>'ai_review_status', ''), '') <> '' OR "
                "COALESCE(NULLIF(BTRIM((" + selected_ai + ")->>'ai_review_comment'), ''), '') <> '')"
            )
        else:
            ai_evidence = (
                "EXISTS (SELECT 1 FROM jsonb_each(v.ai_models_json) kv WHERE "
                "COALESCE(NULLIF(kv.value->>'ai_review_status', ''), '') <> '' OR "
                "COALESCE(NULLIF(BTRIM(kv.value->>'ai_review_comment'), ''), '') <> '')"
            )
        if review_status == "unreviewed":
            where_clauses.append(f"(NOT {human_evidence} AND NOT {ai_evidence})")
        elif review_status == "human":
            where_clauses.append(f"({human_evidence} AND NOT {ai_evidence})")
        elif review_status == "ai":
            where_clauses.append(f"(NOT {human_evidence} AND {ai_evidence})")
        elif review_status == "both":
            where_clauses.append(f"({human_evidence} AND {ai_evidence})")
        else:
            where_clauses.append(f"({human_evidence} OR {ai_evidence})")

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
        valid_statuses = [
            s for s in ai_review_statuses if s and s != AI_REVIEW_STATUS_MISSING
        ]
        include_missing_status = AI_REVIEW_STATUS_MISSING in ai_review_statuses
        if valid_statuses or include_missing_status:
            status_clauses = []
            if selected_ai_model_id is not None:
                selected_ai_review_status = "(v.ai_models_json -> :ai_model_key) ->> 'ai_review_status'"
                if valid_statuses:
                    status_clauses.append(
                        f"{selected_ai_review_status} = ANY(:ai_review_statuses)"
                    )
                if include_missing_status:
                    status_clauses.append(
                        f"COALESCE(NULLIF({selected_ai_review_status}, ''), '') = ''"
                    )
            else:
                if valid_statuses:
                    status_clauses.append(
                        "EXISTS (SELECT 1 FROM jsonb_each(v.ai_models_json) kv "
                        "WHERE kv.value->>'ai_review_status' = ANY(:ai_review_statuses))"
                    )
                if include_missing_status:
                    status_clauses.append(
                        "EXISTS (SELECT 1 FROM jsonb_each(v.ai_models_json) kv "
                        "WHERE COALESCE(NULLIF(kv.value->>'ai_review_status', ''), '') = '')"
                    )
            where_clauses.append(f"({' OR '.join(status_clauses)})")
            if valid_statuses:
                params["ai_review_statuses"] = valid_statuses

    if final_grades:
        valid_final_grades = [g for g in final_grades if g]
        if valid_final_grades:
            where_clauses.append(f"{sql_final_grade_expression(final_grade_basis)} = ANY(:final_grades)")
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
