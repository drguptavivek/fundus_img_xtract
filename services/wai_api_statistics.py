"""Query helpers for WAI API statistics backed by ai_inference_runs_mv."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import ceil
from typing import Any, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from models import LabUnit


RESULT_TYPES = ("positive", "negative", "inconclusive")
INFERENCE_STATUSES = ("success", "failed", "running", "queued")
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class WaiStatsFilters:
    disease_ids: tuple[int, ...] = ()
    project_ids: tuple[int, ...] = ()
    ai_model_ids: tuple[int, ...] = ()
    result_types: tuple[str, ...] = ()
    inference_statuses: tuple[str, ...] = ()
    capture_start: date | None = None
    capture_end: date | None = None
    inference_start: date | None = None
    inference_end: date | None = None


def _clean_ints(values: Iterable[int | str | None]) -> tuple[int, ...]:
    out: list[int] = []
    for value in values:
        try:
            parsed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in out:
            out.append(parsed)
    return tuple(out)


def _clean_choices(values: Iterable[str | None], allowed: tuple[str, ...]) -> tuple[str, ...]:
    allowed_set = set(allowed)
    out: list[str] = []
    for value in values:
        cleaned = (value or "").strip().lower()
        if cleaned in allowed_set and cleaned not in out:
            out.append(cleaned)
    return tuple(out)


def build_filters(
    *,
    disease_ids: Iterable[int | str | None] = (),
    project_ids: Iterable[int | str | None] = (),
    ai_model_ids: Iterable[int | str | None] = (),
    result_types: Iterable[str | None] = (),
    inference_statuses: Iterable[str | None] = (),
    capture_start: date | None = None,
    capture_end: date | None = None,
    inference_start: date | None = None,
    inference_end: date | None = None,
) -> WaiStatsFilters:
    return WaiStatsFilters(
        disease_ids=_clean_ints(disease_ids),
        project_ids=_clean_ints(project_ids),
        ai_model_ids=_clean_ints(ai_model_ids),
        result_types=_clean_choices(result_types, RESULT_TYPES),
        inference_statuses=_clean_choices(inference_statuses, INFERENCE_STATUSES),
        capture_start=capture_start,
        capture_end=capture_end,
        inference_start=inference_start,
        inference_end=inference_end,
    )


def _scope_clause(db: Session, user: Any, params: dict[str, Any]) -> list[str]:
    if user.has_role("admin"):
        return []
    if not getattr(user, "hospital_id", None):
        return ["1 = 0"]

    params["scope_hospital_id"] = user.hospital_id

    if user.has_role("local_admin"):
        lab_unit_ids = [
            row[0]
            for row in db.query(LabUnit.id)
            .filter(LabUnit.hospital_id == user.hospital_id)
            .all()
        ]
    else:
        lab_unit_ids = [
            lab_unit.id
            for lab_unit in getattr(user, "lab_units", []) or []
            if lab_unit.hospital_id == user.hospital_id
        ]
    if lab_unit_ids:
        params["scope_lab_unit_ids"] = tuple(lab_unit_ids)
        return ["(hospital_id = :scope_hospital_id OR lab_unit_id IN :scope_lab_unit_ids)"]
    return ["hospital_id = :scope_hospital_id"]


def _filter_clauses(db: Session, filters: WaiStatsFilters, user: Any, params: dict[str, Any]) -> list[str]:
    clauses = ["is_latest_for_task_model IS TRUE"]
    clauses.extend(_scope_clause(db, user, params))

    if filters.disease_ids:
        clauses.append("disease_id IN :disease_ids")
        params["disease_ids"] = filters.disease_ids
    if filters.project_ids:
        clauses.append("project_id IN :project_ids")
        params["project_ids"] = filters.project_ids
    if filters.ai_model_ids:
        clauses.append("ai_model_id IN :ai_model_ids")
        params["ai_model_ids"] = filters.ai_model_ids
    if filters.result_types:
        clauses.append("result_type IN :result_types")
        params["result_types"] = filters.result_types
    if filters.inference_statuses:
        clauses.append("inference_status IN :inference_statuses")
        params["inference_statuses"] = filters.inference_statuses
    if filters.capture_start:
        clauses.append("normalized_capture_date >= :capture_start")
        params["capture_start"] = filters.capture_start
    if filters.capture_end:
        clauses.append("normalized_capture_date <= :capture_end")
        params["capture_end"] = filters.capture_end
    if filters.inference_start:
        clauses.append("inference_created_at >= :inference_start")
        params["inference_start"] = filters.inference_start
    if filters.inference_end:
        clauses.append("inference_created_at < (CAST(:inference_end AS date) + INTERVAL '1 day')")
        params["inference_end"] = filters.inference_end
    return clauses


def _statement(sql: str, params: dict[str, Any]):
    stmt = text(sql)
    for key in ("scope_lab_unit_ids", "disease_ids", "project_ids", "ai_model_ids", "result_types", "inference_statuses"):
        if key in params:
            stmt = stmt.bindparams(bindparam(key, expanding=True))
    return stmt


def _where_sql(db: Session, filters: WaiStatsFilters, user: Any, params: dict[str, Any]) -> str:
    return " AND ".join(_filter_clauses(db, filters, user, params))


def get_filter_options(db: Session, user: Any) -> dict[str, Any]:
    params: dict[str, Any] = {}
    where_sql = " AND ".join(["is_latest_for_task_model IS TRUE", *_scope_clause(db, user, params)])
    sql = f"""
        SELECT
            COALESCE(
                JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT('id', disease_id, 'label', disease_name))
                FILTER (WHERE disease_id IS NOT NULL),
                '[]'::jsonb
            ) AS diseases,
            COALESCE(
                JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT('id', project_id, 'label', project_title))
                FILTER (WHERE project_id IS NOT NULL),
                '[]'::jsonb
            ) AS projects,
            COALESCE(
                JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT('id', ai_model_id, 'label', ai_model_name || ' ' || ai_model_version))
                FILTER (WHERE ai_model_id IS NOT NULL),
                '[]'::jsonb
            ) AS models
        FROM ai_inference_runs_mv
        WHERE {where_sql}
    """
    row = db.execute(_statement(sql, params), params).mappings().one()
    return {
        "diseases": sorted(row["diseases"] or [], key=lambda item: item["label"] or ""),
        "projects": sorted(row["projects"] or [], key=lambda item: item["label"] or ""),
        "models": sorted(row["models"] or [], key=lambda item: item["label"] or ""),
        "result_types": list(RESULT_TYPES),
        "inference_statuses": list(INFERENCE_STATUSES),
    }


def get_summary(db: Session, user: Any, filters: WaiStatsFilters) -> dict[str, Any]:
    params: dict[str, Any] = {}
    where_sql = _where_sql(db, filters, user, params)
    sql = f"""
        SELECT
            COUNT(DISTINCT image_uuid) FILTER (WHERE image_source <> 'encounter' AND image_uuid IS NOT NULL) AS images,
            COUNT(DISTINCT normalized_patient_encounter_id) FILTER (WHERE normalized_patient_encounter_id IS NOT NULL) AS encounters,
            COUNT(DISTINCT image_uuid) FILTER (WHERE result_type = 'positive' AND image_source <> 'encounter' AND image_uuid IS NOT NULL) AS positive_images,
            COUNT(DISTINCT normalized_patient_encounter_id) FILTER (WHERE result_type = 'positive' AND normalized_patient_encounter_id IS NOT NULL) AS positive_encounters,
            COUNT(*) FILTER (WHERE inference_status = 'failed') AS failed_runs,
            COUNT(*) FILTER (WHERE result_type = 'inconclusive') AS inconclusive_runs
        FROM ai_inference_runs_mv
        WHERE {where_sql}
    """
    row = db.execute(_statement(sql, params), params).mappings().one()

    monthly_sql = f"""
        SELECT
            DATE_TRUNC('month', inference_created_at)::date AS month,
            COUNT(DISTINCT image_uuid) FILTER (WHERE image_source <> 'encounter' AND image_uuid IS NOT NULL) AS images,
            COUNT(DISTINCT normalized_patient_encounter_id) FILTER (WHERE normalized_patient_encounter_id IS NOT NULL) AS encounters,
            COUNT(*) FILTER (WHERE result_type = 'positive') AS positive,
            COUNT(*) FILTER (WHERE result_type = 'negative') AS negative,
            COUNT(*) FILTER (WHERE result_type = 'inconclusive') AS inconclusive,
            COUNT(*) FILTER (WHERE inference_status = 'failed') AS failed
        FROM ai_inference_runs_mv
        WHERE {where_sql}
        GROUP BY DATE_TRUNC('month', inference_created_at)
        ORDER BY month DESC
        LIMIT 18
    """
    monthly = [dict(item) for item in db.execute(_statement(monthly_sql, params), params).mappings().all()]
    return {"cards": dict(row), "monthly": monthly}


def _pagination(total: int, page: int, page_size: int) -> dict[str, int]:
    total_pages = max(1, ceil(total / page_size))
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def _normalize_page(page: int | None, page_size: int | None) -> tuple[int, int]:
    clean_page = max(1, int(page or 1))
    clean_page_size = min(MAX_PAGE_SIZE, max(1, int(page_size or DEFAULT_PAGE_SIZE)))
    return clean_page, clean_page_size


def get_image_results(db: Session, user: Any, filters: WaiStatsFilters, *, page: int | None, page_size: int | None) -> dict[str, Any]:
    clean_page, clean_page_size = _normalize_page(page, page_size)
    offset = (clean_page - 1) * clean_page_size
    params: dict[str, Any] = {"limit": clean_page_size, "offset": offset}
    where_sql = _where_sql(db, filters, user, params)
    where_sql = f"{where_sql} AND image_source <> 'encounter' AND image_uuid IS NOT NULL"

    total = db.execute(
        _statement(f"SELECT COUNT(*) FROM ai_inference_runs_mv WHERE {where_sql}", params),
        params,
    ).scalar_one()
    sql = f"""
        SELECT
            inference_run_id,
            task_id,
            task_uuid,
            disease_name,
            project_title,
            image_source,
            image_uuid,
            image_filename,
            normalized_patient_encounter_id,
            encounter_name,
            patient_identifier,
            normalized_capture_date,
            inference_created_at,
            inference_finished_at,
            ai_model_name,
            ai_model_version,
            inference_status,
            result_type,
            ai_grade_name,
            ai_probability,
            api_prediction,
            api_predicted_class,
            api_predicted_class_name,
            http_status,
            error_code,
            error_message
        FROM ai_inference_runs_mv
        WHERE {where_sql}
        ORDER BY inference_created_at DESC, inference_run_id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = [dict(row) for row in db.execute(_statement(sql, params), params).mappings().all()]
    return {"rows": rows, "pagination": _pagination(int(total), clean_page, clean_page_size)}


def get_encounter_results(db: Session, user: Any, filters: WaiStatsFilters, *, page: int | None, page_size: int | None) -> dict[str, Any]:
    clean_page, clean_page_size = _normalize_page(page, page_size)
    offset = (clean_page - 1) * clean_page_size
    params: dict[str, Any] = {"limit": clean_page_size, "offset": offset}
    where_sql = _where_sql(db, filters, user, params)
    where_sql = f"{where_sql} AND normalized_patient_encounter_id IS NOT NULL"

    grouped = f"""
        SELECT
            normalized_patient_encounter_id,
            MAX(patient_encounter_uuid) AS patient_encounter_uuid,
            MAX(encounter_name) AS encounter_name,
            MAX(patient_identifier) AS patient_identifier,
            MAX(project_title) AS project_title,
            MAX(normalized_capture_date) AS normalized_capture_date,
            MAX(inference_created_at) AS latest_inference_at,
            COUNT(DISTINCT image_uuid) FILTER (WHERE image_source <> 'encounter' AND image_uuid IS NOT NULL) AS image_count,
            COUNT(*) AS run_count,
            COUNT(*) FILTER (WHERE inference_status = 'failed') AS failed_count,
            COUNT(*) FILTER (WHERE result_type = 'positive') AS positive_count,
            COUNT(*) FILTER (WHERE result_type = 'negative') AS negative_count,
            COUNT(*) FILTER (WHERE result_type = 'inconclusive') AS inconclusive_count,
            CASE
                WHEN COUNT(*) FILTER (WHERE result_type = 'positive') > 0 THEN 'positive'
                WHEN COUNT(*) FILTER (WHERE result_type = 'inconclusive') > 0 THEN 'inconclusive'
                WHEN COUNT(*) FILTER (WHERE inference_status <> 'success') > 0 THEN 'inconclusive'
                WHEN COUNT(*) FILTER (WHERE result_type = 'negative') = COUNT(*) THEN 'negative'
                ELSE 'inconclusive'
            END AS encounter_result_type,
            JSONB_AGG(
                JSONB_BUILD_OBJECT(
                    'image_uuid', image_uuid,
                    'image_filename', image_filename,
                    'disease_name', disease_name,
                    'model', ai_model_name || ' ' || ai_model_version,
                    'status', inference_status,
                    'result_type', result_type,
                    'ai_grade_name', ai_grade_name,
                    'ai_probability', ai_probability,
                    'inference_created_at', inference_created_at
                )
                ORDER BY inference_created_at DESC, inference_run_id DESC
            ) FILTER (WHERE image_uuid IS NOT NULL) AS image_results
        FROM ai_inference_runs_mv
        WHERE {where_sql}
        GROUP BY normalized_patient_encounter_id
    """
    total_sql = f"SELECT COUNT(*) FROM ({grouped}) encounter_rows"
    total = db.execute(_statement(total_sql, params), params).scalar_one()
    sql = f"""
        SELECT *
        FROM ({grouped}) encounter_rows
        ORDER BY latest_inference_at DESC, normalized_patient_encounter_id DESC
        LIMIT :limit OFFSET :offset
    """
    rows = [dict(row) for row in db.execute(_statement(sql, params), params).mappings().all()]
    return {"rows": rows, "pagination": _pagination(int(total), clean_page, clean_page_size)}
