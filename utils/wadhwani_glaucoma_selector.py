from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

from models import AIModelIntegration, Disease, DiseaseGrading
from utils.final_grade_basis import (
    FINAL_GRADE_BASIS_DOUBLE_MATCH,
    normalize_final_grade_basis,
    sql_final_grade_expression,
)
from utils.mvw_image_listing_v2 import get_mv_name_for_disease

WADHWANI_PROVIDER = "wadhwani_glaucoma"
MAX_MANUAL_WADHWANI_BATCH = 100
DEFAULT_MANUAL_WADHWANI_LIMIT = 20
PRE_GRADED_UPLOAD_TYPE = "Pregraded"


@dataclass
class WadhwaniEligibleTaskRow:
    task_id: int
    task_uuid: str
    source_type: str
    image_uuid: str | None
    image_filename: str | None
    hospital_name: str | None
    lab_unit_name: str | None
    camera_name: str | None
    final_grade_name: str | None
    remedio_result: str | None
    vcdr_right_num: float | None
    vcdr_left_num: float | None
    laterality: str | None
    centering: str | None
    capture_date: Any
    upload_date: Any
    created_at: Any


def get_linked_wadhwani_integration(db) -> AIModelIntegration | None:
    return db.execute(
        select(AIModelIntegration)
        .where(AIModelIntegration.provider == WADHWANI_PROVIDER)
        .where(AIModelIntegration.is_enabled.is_(True))
        .order_by(AIModelIntegration.updated_at.desc(), AIModelIntegration.id.desc())
    ).scalars().first()


def get_glaucoma_disease(db) -> Disease | None:
    return db.execute(
        select(Disease).where(Disease.name.ilike("glaucoma"))
    ).scalar_one_or_none()


def get_glaucoma_grade_options(db) -> list[str]:
    glaucoma = get_glaucoma_disease(db)
    if glaucoma is None:
        return []
    return [
        row[0]
        for row in db.execute(
            select(DiseaseGrading.impression)
            .where(DiseaseGrading.disease_id == glaucoma.id)
            .where(DiseaseGrading.is_active.is_(True))
            .order_by(DiseaseGrading.display_order, DiseaseGrading.impression)
        ).all()
    ]


def list_zip_glaucoma_result_options(db) -> list[str]:
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT grc.result
            FROM glaucoma_results_cleaned grc
            WHERE grc.result IS NOT NULL
            ORDER BY grc.result
            """
        )
    ).all()
    return [row[0] for row in rows]


def list_eligible_wadhwani_glaucoma_tasks(
    db,
    *,
    ai_model_id: int,
    allowed_lab_unit_ids: list[int],
    filters: dict[str, Any],
) -> list[WadhwaniEligibleTaskRow]:
    source_type = (filters.get("source_type") or "").strip().lower()
    if source_type not in {"zip", "direct", "pregraded"}:
        return []

    glaucoma = get_glaucoma_disease(db)
    if glaucoma is None or not allowed_lab_unit_ids:
        return []

    mv_name = get_mv_name_for_disease(db, glaucoma.id)
    final_grade_basis = normalize_final_grade_basis(filters.get("final_grade_basis") or FINAL_GRADE_BASIS_DOUBLE_MATCH)
    final_grade_expr = sql_final_grade_expression(final_grade_basis)

    where_clauses = [
        "v.disease_id = :disease_id",
        "v.task_lab_unit_id = ANY(:allowed_lab_units)",
        "v.task_id IS NOT NULL",
        """NOT EXISTS (
            SELECT 1
            FROM grades g
            WHERE g.task_id = v.task_id
              AND g.role_slot = 'ai'
              AND g.ai_model_id = :ai_model_id
        )""",
    ]
    params: dict[str, Any] = {
        "disease_id": glaucoma.id,
        "allowed_lab_units": allowed_lab_unit_ids,
        "ai_model_id": ai_model_id,
        "limit": _normalized_limit(filters.get("limit")),
    }

    if source_type == "zip":
        where_clauses.extend(
            [
                "v.upload_type = 'ZIP'",
                "v.encounter_file_id IS NOT NULL",
            ]
        )
    elif source_type == "direct":
        where_clauses.extend(
            [
                "v.upload_type = 'Direct'",
                "v.direct_image_upload_id IS NOT NULL",
            ]
        )
    else:
        where_clauses.extend(
            [
                "v.upload_type = :pregraded_upload_type",
                "v.direct_image_upload_id IS NOT NULL",
            ]
        )
        params["pregraded_upload_type"] = PRE_GRADED_UPLOAD_TYPE

    lab_unit_id = _optional_int(filters.get("lab_unit_id"))
    if lab_unit_id:
        where_clauses.append("v.task_lab_unit_id = :lab_unit_id")
        params["lab_unit_id"] = lab_unit_id

    final_grade_name = (filters.get("final_grade_name") or "").strip() or None
    if final_grade_name:
        where_clauses.append(f"{final_grade_expr} = :final_grade_name")
        params["final_grade_name"] = final_grade_name

    if source_type == "zip":
        zip_camera_id = _optional_int(filters.get("zip_camera_id"))
        if zip_camera_id:
            where_clauses.append("ef.camera_id = :zip_camera_id")
            params["zip_camera_id"] = zip_camera_id

        laterality = (filters.get("laterality") or "").strip().lower()
        if laterality:
            where_clauses.append("LOWER(COALESCE(ef.eye_side, '')) = :laterality")
            params["laterality"] = laterality

        centering = (filters.get("centering") or "").strip().lower()
        if centering:
            where_clauses.append("LOWER(COALESCE(ef.centering, '')) = :centering")
            params["centering"] = centering

        remedio_result = (filters.get("remedio_result") or "").strip()
        if remedio_result:
            where_clauses.append("grc.result = :remedio_result")
            params["remedio_result"] = remedio_result

        vcdr_min = _optional_float(filters.get("vcdr_min"))
        if vcdr_min is not None:
            where_clauses.append(
                "GREATEST(COALESCE(grc.vcdr_right_num, -1), COALESCE(grc.vcdr_left_num, -1)) >= :vcdr_min"
            )
            params["vcdr_min"] = vcdr_min

        vcdr_max = _optional_float(filters.get("vcdr_max"))
        if vcdr_max is not None:
            where_clauses.append(
                "GREATEST(COALESCE(grc.vcdr_right_num, -1), COALESCE(grc.vcdr_left_num, -1)) <= :vcdr_max"
            )
            params["vcdr_max"] = vcdr_max

        capture_date_from = (filters.get("capture_date_from") or "").strip()
        if capture_date_from:
            where_clauses.append("v.capture_date >= :capture_date_from")
            params["capture_date_from"] = capture_date_from

        capture_date_to = (filters.get("capture_date_to") or "").strip()
        if capture_date_to:
            where_clauses.append("v.capture_date <= :capture_date_to")
            params["capture_date_to"] = capture_date_to
    else:
        hospital_id = _optional_int(filters.get("hospital_id"))
        if hospital_id:
            where_clauses.append("v.hospital_id = :hospital_id")
            params["hospital_id"] = hospital_id

        direct_camera_id = _optional_int(filters.get("direct_camera_id"))
        if direct_camera_id:
            where_clauses.append("v.camera_id = :direct_camera_id")
            params["direct_camera_id"] = direct_camera_id

        upload_date_from = (filters.get("upload_date_from") or "").strip()
        if upload_date_from:
            where_clauses.append("v.upload_date_utc >= :upload_date_from")
            params["upload_date_from"] = upload_date_from

        upload_date_to = (filters.get("upload_date_to") or "").strip()
        if upload_date_to:
            where_clauses.append("v.upload_date_utc <= :upload_date_to")
            params["upload_date_to"] = upload_date_to

    where_sql = " AND ".join(where_clauses)
    if source_type == "zip":
        sql = text(
            f"""
            SELECT
                v.task_id,
                v.task_uuid,
                v.upload_type,
                v.image_uuid,
                v.image_filename,
                v.hospital_name,
                v.lab_unit_name,
                cam.name AS camera_name,
                {final_grade_expr} AS final_grade_name,
                grc.result AS glaucoma_result,
                grc.vcdr_right_num AS glaucoma_vcdr_right_num,
                grc.vcdr_left_num AS glaucoma_vcdr_left_num,
                ef.eye_side,
                ef.centering,
                v.capture_date,
                v.upload_date_utc
            FROM {mv_name} v
            JOIN encounter_files ef ON ef.id = v.encounter_file_id
            LEFT JOIN cameras cam ON cam.id = ef.camera_id
            LEFT JOIN patient_encounters pe ON pe.id = v.patient_encounter_id
            LEFT JOIN glaucoma_results_cleaned grc ON grc.patient_encounter_id = pe.id
            WHERE {where_sql}
            ORDER BY v.task_id DESC
            LIMIT :limit
            """
        )
    else:
        sql = text(
            f"""
            SELECT
                v.task_id,
                v.task_uuid,
                v.upload_type,
                v.image_uuid,
                v.image_filename,
                v.hospital_name,
                v.lab_unit_name,
                v.camera_name,
                {final_grade_expr} AS final_grade_name,
                NULL::text AS glaucoma_result,
                NULL::double precision AS glaucoma_vcdr_right_num,
                NULL::double precision AS glaucoma_vcdr_left_num,
                NULL::text AS eye_side,
                NULL::text AS centering,
                v.capture_date,
                v.upload_date_utc
            FROM {mv_name} v
            WHERE {where_sql}
            ORDER BY v.task_id DESC
            LIMIT :limit
            """
        )
    rows = db.execute(sql, params).fetchall()
    return [
        WadhwaniEligibleTaskRow(
            task_id=row.task_id,
            task_uuid=row.task_uuid,
            source_type=row.upload_type.lower(),
            image_uuid=row.image_uuid,
            image_filename=row.image_filename,
            hospital_name=row.hospital_name,
            lab_unit_name=row.lab_unit_name,
            camera_name=row.camera_name,
            final_grade_name=row.final_grade_name,
            remedio_result=row.glaucoma_result,
            vcdr_right_num=row.glaucoma_vcdr_right_num,
            vcdr_left_num=row.glaucoma_vcdr_left_num,
            laterality=row.eye_side,
            centering=row.centering,
            capture_date=row.capture_date,
            upload_date=row.upload_date_utc,
            created_at=row.upload_date_utc,
        )
        for row in rows
    ]


def filter_still_eligible_task_ids(
    db,
    *,
    ai_model_id: int,
    allowed_lab_unit_ids: list[int],
    task_ids: list[int],
) -> list[int]:
    if not task_ids:
        return []

    glaucoma = get_glaucoma_disease(db)
    if glaucoma is None or not allowed_lab_unit_ids:
        return []

    mv_name = get_mv_name_for_disease(db, glaucoma.id)
    rows = db.execute(
        text(
            f"""
            SELECT v.task_id
            FROM {mv_name} v
            WHERE v.task_id = ANY(:task_ids)
              AND v.task_lab_unit_id = ANY(:allowed_lab_units)
              AND NOT EXISTS (
                SELECT 1
                FROM grades g
                WHERE g.task_id = v.task_id
                  AND g.role_slot = 'ai'
                  AND g.ai_model_id = :ai_model_id
              )
              AND (
                (v.upload_type = 'ZIP' AND v.encounter_file_id IS NOT NULL) OR
                (v.upload_type IN ('Direct', :pregraded_upload_type) AND v.direct_image_upload_id IS NOT NULL)
              )
            """
        ),
        {
            "task_ids": task_ids,
            "allowed_lab_units": allowed_lab_unit_ids,
            "ai_model_id": ai_model_id,
            "pregraded_upload_type": PRE_GRADED_UPLOAD_TYPE,
        },
    ).all()
    eligible_ids = {row[0] for row in rows}
    return [task_id for task_id in task_ids if task_id in eligible_ids]


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_limit(value: Any) -> int:
    try:
        limit = int(value or DEFAULT_MANUAL_WADHWANI_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_MANUAL_WADHWANI_LIMIT
    return max(1, min(limit, MAX_MANUAL_WADHWANI_BATCH))
