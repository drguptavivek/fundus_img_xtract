from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from flask import jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from auth.roles import roles_required
from authz.behaviors import analytics_lab_units, analytics_rows
from db_transaction_manager import get_db_session
from models import (
    DirectImageUpload,
    EncounterFile,
    EncounterSetImage,
    GradingTask,
    LabUnit,
    PatientEncounters,
)
from services.uploads.access import encounter_columns, upload_columns
from tasks.access import task_columns
from tasks.lineage import valid_task_lineage
from utils.log_sanitize import sanitize_log_value

from . import bp


def _scoped_lab_unit_ids() -> list[int]:
    """Return all Lab Units currently authorized for analytics."""
    with get_db_session() as db:
        query = analytics_lab_units(db, db.query(LabUnit.id), current_user)
        return sorted(int(row[0]) for row in query.all())


def _optional_int(name: str) -> int | None:
    """Parse a positive filter, preserving malformed values as no-match.

    ``request.args.get(..., type=int)`` turns an invalid supplied value into
    ``None``.  Treating that as an omitted filter broadens the query, so an
    invalid value is represented by ``-1`` and can only produce zero rows.
    """
    raw_value = request.args.get(name)
    if raw_value is None:
        return None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return -1
    return value if value > 0 else -1


def _authorized_task_ids(
    db: Session,
    *,
    disease_id: int | None = None,
    lab_unit_id: int | None = None,
    hospital_id: int | None = None,
) -> list[int]:
    """Return the exact task identities visible to this analytics request.

    The materialized view is an efficient calculation source, not an
    authorization source.  Resolve task lineage through the normal
    ``analytics_rows`` behaviour first, including project grants and the
    LabUnit -> Hospital relationship, then constrain every MV read by these
    identities.  This prevents a project sharing a LabUnit from inheriting
    another project's rows.
    """
    query = db.query(GradingTask.id).join(
        LabUnit, GradingTask.lab_unit_id == LabUnit.id
    )
    query = analytics_rows(
        db,
        query,
        current_user,
        task_columns(GradingTask, hospital_id_column=LabUnit.hospital_id),
    )
    query = query.filter(
        GradingTask.lab_unit_id.is_not(None),
        LabUnit.hospital_id.is_not(None),
        valid_task_lineage(),
    )
    if disease_id is not None:
        query = query.filter(GradingTask.disease_id == disease_id)
    if lab_unit_id is not None:
        query = query.filter(GradingTask.lab_unit_id == lab_unit_id)
    if hospital_id is not None:
        query = query.filter(LabUnit.hospital_id == hospital_id)
    return [int(row[0]) for row in query.all()]


def _valid_task_lineage():
    """Require a complete, internally consistent source-task lineage.

    ``admin_rows`` intentionally permits every actor, so these predicates
    must remain independent of actor scope.  They mirror the maintained task
    project invariant and reject malformed source links, including a child
    row disagreeing with its parent encounter.
    """
    source_shape = or_(
        and_(
            GradingTask.encounter_file_id.is_not(None),
            GradingTask.direct_image_upload_id.is_(None),
            GradingTask.patient_encounter_id.is_(None),
            GradingTask.encounter_set_image_id.is_(None),
        ),
        and_(
            GradingTask.encounter_file_id.is_(None),
            GradingTask.direct_image_upload_id.is_not(None),
            GradingTask.patient_encounter_id.is_(None),
            GradingTask.encounter_set_image_id.is_(None),
        ),
        and_(
            GradingTask.encounter_file_id.is_(None),
            GradingTask.direct_image_upload_id.is_(None),
            GradingTask.patient_encounter_id.is_not(None),
            GradingTask.encounter_set_image_id.is_(None),
        ),
        and_(
            GradingTask.encounter_file_id.is_(None),
            GradingTask.direct_image_upload_id.is_(None),
            GradingTask.patient_encounter_id.is_(None),
            GradingTask.encounter_set_image_id.is_not(None),
        ),
    )
    encounter_file_lineage = exists(
        select(1)
        .select_from(EncounterFile)
        .join(
            PatientEncounters,
            PatientEncounters.id == EncounterFile.patient_encounter_id,
        )
        .where(
            EncounterFile.id == GradingTask.encounter_file_id,
            PatientEncounters.lab_unit_id == GradingTask.lab_unit_id,
            or_(
                EncounterFile.lab_unit_id.is_(None),
                EncounterFile.lab_unit_id == GradingTask.lab_unit_id,
            ),
            or_(
                EncounterFile.hospital_id.is_(None),
                EncounterFile.hospital_id == LabUnit.hospital_id,
            ),
            or_(
                EncounterFile.project_id.is_(None),
                EncounterFile.project_id == PatientEncounters.project_id,
            ),
            PatientEncounters.project_id.is_not_distinct_from(
                GradingTask.project_id
            ),
        )
    )
    direct_upload_lineage = exists(
        select(1)
        .select_from(DirectImageUpload)
        .where(
            DirectImageUpload.id == GradingTask.direct_image_upload_id,
            DirectImageUpload.lab_unit_id == GradingTask.lab_unit_id,
            DirectImageUpload.hospital_id == LabUnit.hospital_id,
            DirectImageUpload.project_id.is_not_distinct_from(
                GradingTask.project_id
            ),
        )
    )
    encounter_lineage = exists(
        select(1)
        .select_from(PatientEncounters)
        .where(
            PatientEncounters.id == GradingTask.patient_encounter_id,
            PatientEncounters.lab_unit_id == GradingTask.lab_unit_id,
            PatientEncounters.project_id.is_not_distinct_from(
                GradingTask.project_id
            ),
        )
    )
    encounter_set_image_lineage = exists(
        select(1)
        .select_from(EncounterSetImage)
        .join(
            PatientEncounters,
            PatientEncounters.id == EncounterSetImage.patient_encounter_id,
        )
        .where(
            EncounterSetImage.id == GradingTask.encounter_set_image_id,
            or_(
                EncounterSetImage.hospital_id.is_(None),
                EncounterSetImage.hospital_id == LabUnit.hospital_id,
            ),
            PatientEncounters.lab_unit_id == GradingTask.lab_unit_id,
            or_(
                EncounterSetImage.project_id.is_(None),
                EncounterSetImage.project_id == PatientEncounters.project_id,
            ),
            PatientEncounters.project_id.is_not_distinct_from(
                GradingTask.project_id
            ),
        )
    )
    return and_(
        GradingTask.lab_unit_id.is_not(None),
        source_shape,
        or_(
            and_(GradingTask.encounter_file_id.is_not(None), encounter_file_lineage),
            and_(GradingTask.direct_image_upload_id.is_not(None), direct_upload_lineage),
            and_(GradingTask.patient_encounter_id.is_not(None), encounter_lineage),
            and_(GradingTask.encounter_set_image_id.is_not(None), encounter_set_image_lineage),
        ),
    )


def _authorized_encounter_ids(
    db: Session,
    *,
    disease_id: int | None = None,
    lab_unit_id: int | None = None,
    hospital_id: int | None = None,
) -> list[int]:
    """Resolve structurally valid, analytics-visible encounter identities."""
    query = db.query(PatientEncounters.id).join(
        LabUnit, PatientEncounters.lab_unit_id == LabUnit.id
    ).filter(
        PatientEncounters.lab_unit_id.is_not(None),
        LabUnit.hospital_id.is_not(None),
    )
    query = analytics_rows(
        db, query, current_user, encounter_columns(PatientEncounters)
    )
    if disease_id is not None:
        query = query.filter(PatientEncounters.disease_id == disease_id)
    if lab_unit_id is not None:
        query = query.filter(PatientEncounters.lab_unit_id == lab_unit_id)
    if hospital_id is not None:
        query = query.filter(LabUnit.hospital_id == hospital_id)
    return [int(row[0]) for row in query.all()]


def _authorized_direct_upload_ids(
    db: Session,
    *,
    disease_id: int | None = None,
    lab_unit_id: int | None = None,
    hospital_id: int | None = None,
) -> list[int]:
    """Resolve direct uploads with canonical Lab Unit/Hospital lineage."""
    query = db.query(DirectImageUpload.id).join(
        LabUnit, DirectImageUpload.lab_unit_id == LabUnit.id
    ).filter(
        DirectImageUpload.lab_unit_id.is_not(None),
        DirectImageUpload.hospital_id.is_not(None),
        LabUnit.hospital_id.is_not(None),
        DirectImageUpload.hospital_id == LabUnit.hospital_id,
    )
    query = analytics_rows(
        db, query, current_user, upload_columns(DirectImageUpload)
    )
    if disease_id is not None:
        query = query.filter(DirectImageUpload.disease_id == disease_id)
    if lab_unit_id is not None:
        query = query.filter(DirectImageUpload.lab_unit_id == lab_unit_id)
    if hospital_id is not None:
        query = query.filter(DirectImageUpload.hospital_id == hospital_id)
    return [int(row[0]) for row in query.all()]


def _base_scoped_tasks_sql(authorized_task_ids: list[int]) -> tuple[sa.TextClause, dict[str, Any]]:
    base_sql = sa.text(
        """
        WITH scoped_tasks AS (
            SELECT DISTINCT
                task_id,
                disease_id,
                disease_name,
                lab_unit_id,
                lab_unit_name,
                hospital_id,
                hospital_name,
                task_state
            FROM mvw_grading_data_all
            WHERE task_id IS NOT NULL
              AND task_id IN :authorized_task_ids
              AND (:disease_id IS NULL OR disease_id = :disease_id)
              AND (:lab_unit_id IS NULL OR lab_unit_id = :lab_unit_id)
              AND (:hospital_id IS NULL OR hospital_id = :hospital_id)
        )
        """
    ).bindparams(sa.bindparam("authorized_task_ids", expanding=True))

    params: dict[str, Any] = {
        "authorized_task_ids": authorized_task_ids or [-1],
        "disease_id": _optional_int("disease_id"),
        "lab_unit_id": _optional_int("lab_unit_id"),
        "hospital_id": _optional_int("hospital_id"),
    }
    return base_sql, params


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator * 100.0) / denominator, 2)


_NOT_GRADABLE_LABELS_SQL = (
    "'not gradable', 'notgradable', 'ungradable', 'not_gradable', 'not-gradable'"
)

_NORMALIZED_NOT_GRADABLE_EXPR_SQL = (
    "lower(trim(regexp_replace(COALESCE(%s, ''), '\\s+', ' ', 'g')))"
)

@bp.route("/hospital-dashboard", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def hospital_dashboard_page():
    lab_unit_ids = _scoped_lab_unit_ids()
    if not lab_unit_ids:
        return render_template(
            "analytics/hospital_dashboard.html",
            hospitals=[],
            lab_units=[],
            diseases=[],
            lab_unit_scope_count=0,
        )

    with get_db_session() as db:
        authorized_task_ids = _authorized_task_ids(db)
    params: dict[str, Any] = {"lab_unit_ids": lab_unit_ids, "authorized_task_ids": authorized_task_ids or [-1]}
    options_sql = sa.text(
        """
        WITH scoped_labs AS (
            SELECT
                lu.id AS lab_unit_id,
                lu.name AS lab_unit_name,
                h.id AS hospital_id,
                h.name AS hospital_name
            FROM lab_units lu
            LEFT JOIN hospitals h ON h.id = lu.hospital_id
            WHERE lu.id IN :lab_unit_ids
        ),
        scoped_diseases AS (
            SELECT DISTINCT
                disease_id,
                disease_name
            FROM mvw_grading_data_all
            WHERE task_id IS NOT NULL
              AND task_id IN :authorized_task_ids
              AND disease_id IS NOT NULL
        )
        SELECT
            sl.hospital_id,
            sl.hospital_name,
            sl.lab_unit_id,
            sl.lab_unit_name,
            sd.disease_id,
            sd.disease_name
        FROM scoped_labs sl
        LEFT JOIN scoped_diseases sd ON TRUE
        ORDER BY sl.hospital_name, sl.lab_unit_name, sd.disease_name
        """
    ).bindparams(
        sa.bindparam("lab_unit_ids", expanding=True),
        sa.bindparam("authorized_task_ids", expanding=True),
    )

    with get_db_session() as db:
        rows = db.execute(options_sql, params).mappings().all()

    hospitals_map: dict[int, dict[str, Any]] = {}
    lab_units_map: dict[int, dict[str, Any]] = {}
    diseases_map: dict[int, dict[str, Any]] = {}

    for row in rows:
        hospital_id = row["hospital_id"]
        if hospital_id and hospital_id not in hospitals_map:
            hospitals_map[hospital_id] = {
                "id": int(hospital_id),
                "name": row["hospital_name"] or f"Hospital {hospital_id}",
            }

        lab_unit_id = row["lab_unit_id"]
        if lab_unit_id and lab_unit_id not in lab_units_map:
            lab_units_map[lab_unit_id] = {
                "id": int(lab_unit_id),
                "name": row["lab_unit_name"] or f"Lab Unit {lab_unit_id}",
                "hospital_id": int(hospital_id) if hospital_id else None,
            }

        disease_id = row["disease_id"]
        if disease_id and disease_id not in diseases_map:
            diseases_map[disease_id] = {
                "id": int(disease_id),
                "name": row["disease_name"] or f"Disease {disease_id}",
            }

    hospitals = sorted(hospitals_map.values(), key=lambda item: item["name"].lower())
    lab_units = sorted(lab_units_map.values(), key=lambda item: item["name"].lower())
    diseases = sorted(diseases_map.values(), key=lambda item: item["name"].lower())

    return render_template(
        "analytics/hospital_dashboard.html",
        hospitals=hospitals,
        lab_units=lab_units,
        diseases=diseases,
        lab_unit_scope_count=len(lab_unit_ids),
    )


@bp.route("/api/hospital-dashboard/disease-view", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def hospital_dashboard_disease_view():
    lab_unit_ids = _scoped_lab_unit_ids()
    if not lab_unit_ids:
        return jsonify({"data": [], "meta": {"lab_unit_scope_count": 0}})

    with get_db_session() as db:
        authorized_task_ids = _authorized_task_ids(
            db,
            disease_id=_optional_int("disease_id"),
            lab_unit_id=_optional_int("lab_unit_id"),
            hospital_id=_optional_int("hospital_id"),
        )
    base_sql, params = _base_scoped_tasks_sql(authorized_task_ids)
    query_sql = sa.text(
        f"""
        {base_sql.text}
        , not_gradable_tasks AS (
            SELECT DISTINCT task_id
            FROM mvw_grading_data_all
            WHERE task_id IS NOT NULL
              AND task_id IN :authorized_task_ids
              AND (:disease_id IS NULL OR disease_id = :disease_id)
              AND (:lab_unit_id IS NULL OR lab_unit_id = :lab_unit_id)
              AND (:hospital_id IS NULL OR hospital_id = :hospital_id)
              AND (
                    {_NORMALIZED_NOT_GRADABLE_EXPR_SQL % "grade_name"} IN ({_NOT_GRADABLE_LABELS_SQL})
                 OR {_NORMALIZED_NOT_GRADABLE_EXPR_SQL % "consensus_final_grade_name"} IN ({_NOT_GRADABLE_LABELS_SQL})
              )
        )
        SELECT
            st.disease_id,
            st.disease_name,
            COUNT(*)::int AS total_tasks,
            SUM(CASE WHEN st.task_state = 'pending' THEN 1 ELSE 0 END)::int AS pending_resident,
            SUM(CASE WHEN st.task_state = 'resident_done' THEN 1 ELSE 0 END)::int AS pending_resident2,
            SUM(CASE WHEN st.task_state = 'arbitration' THEN 1 ELSE 0 END)::int AS pending_arbitration,
            SUM(CASE WHEN ngt.task_id IS NOT NULL THEN 1 ELSE 0 END)::int AS non_gradable_count
        FROM scoped_tasks st
        LEFT JOIN not_gradable_tasks ngt ON ngt.task_id = st.task_id
        GROUP BY st.disease_id, st.disease_name
        ORDER BY st.disease_name
        """
    ).bindparams(sa.bindparam("authorized_task_ids", expanding=True))

    with get_db_session() as db:
        rows = db.execute(query_sql, params).mappings().all()

    data: list[dict[str, Any]] = []
    overall_total_tasks = 0
    overall_non_gradable_count = 0
    for row in rows:
        total = int(row["total_tasks"] or 0)
        pending_resident = int(row["pending_resident"] or 0)
        pending_resident2 = int(row["pending_resident2"] or 0)
        pending_arbitration = int(row["pending_arbitration"] or 0)
        non_gradable_count = int(row["non_gradable_count"] or 0)
        overall_total_tasks += total
        overall_non_gradable_count += non_gradable_count
        data.append(
            {
                "disease_id": row["disease_id"],
                "disease_name": row["disease_name"],
                "total_tasks": total,
                "pending_resident": pending_resident,
                "pending_resident_pct": _pct(pending_resident, total),
                "pending_resident2": pending_resident2,
                "pending_resident2_pct": _pct(pending_resident2, total),
                "pending_arbitration": pending_arbitration,
                "pending_arbitration_pct": _pct(pending_arbitration, total),
                "non_gradable_count": non_gradable_count,
                "non_gradable_pct": _pct(non_gradable_count, total),
            }
        )

    return jsonify(
        {
            "data": data,
            "meta": {
                "lab_unit_scope_count": len(lab_unit_ids),
                "cumulative_total_tasks": overall_total_tasks,
                "cumulative_non_gradable_count": overall_non_gradable_count,
                "cumulative_non_gradable_pct": _pct(overall_non_gradable_count, overall_total_tasks),
                "filters": {
                    "disease_id": params["disease_id"],
                    "lab_unit_id": params["lab_unit_id"],
                    "hospital_id": params["hospital_id"],
                },
            },
        }
    )


@bp.route("/api/hospital-dashboard/lab-disease-view", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def hospital_dashboard_lab_disease_view():
    lab_unit_ids = _scoped_lab_unit_ids()
    if not lab_unit_ids:
        return jsonify({"data": [], "meta": {"lab_unit_scope_count": 0}})

    with get_db_session() as db:
        authorized_task_ids = _authorized_task_ids(
            db,
            disease_id=_optional_int("disease_id"),
            lab_unit_id=_optional_int("lab_unit_id"),
            hospital_id=_optional_int("hospital_id"),
        )
    base_sql, params = _base_scoped_tasks_sql(authorized_task_ids)
    query_sql = sa.text(
        f"""
        {base_sql.text}
        , not_gradable_tasks AS (
            SELECT DISTINCT task_id
            FROM mvw_grading_data_all
            WHERE task_id IS NOT NULL
              AND task_id IN :authorized_task_ids
              AND (:disease_id IS NULL OR disease_id = :disease_id)
              AND (:lab_unit_id IS NULL OR lab_unit_id = :lab_unit_id)
              AND (:hospital_id IS NULL OR hospital_id = :hospital_id)
              AND (
                    {_NORMALIZED_NOT_GRADABLE_EXPR_SQL % "grade_name"} IN ({_NOT_GRADABLE_LABELS_SQL})
                 OR {_NORMALIZED_NOT_GRADABLE_EXPR_SQL % "consensus_final_grade_name"} IN ({_NOT_GRADABLE_LABELS_SQL})
              )
        )
        SELECT
            st.hospital_id,
            st.hospital_name,
            st.lab_unit_id,
            st.lab_unit_name,
            st.disease_id,
            st.disease_name,
            COUNT(*)::int AS total_tasks,
            SUM(CASE WHEN st.task_state = 'pending' THEN 1 ELSE 0 END)::int AS pending_resident,
            SUM(CASE WHEN st.task_state = 'resident_done' THEN 1 ELSE 0 END)::int AS pending_resident2,
            SUM(CASE WHEN st.task_state = 'arbitration' THEN 1 ELSE 0 END)::int AS pending_arbitration,
            SUM(CASE WHEN ngt.task_id IS NOT NULL THEN 1 ELSE 0 END)::int AS non_gradable_count
        FROM scoped_tasks st
        LEFT JOIN not_gradable_tasks ngt ON ngt.task_id = st.task_id
        GROUP BY
            st.hospital_id, st.hospital_name,
            st.lab_unit_id, st.lab_unit_name,
            st.disease_id, st.disease_name
        ORDER BY st.hospital_name, st.lab_unit_name, st.disease_name
        """
    ).bindparams(sa.bindparam("authorized_task_ids", expanding=True))

    with get_db_session() as db:
        rows = db.execute(query_sql, params).mappings().all()

    data: list[dict[str, Any]] = []
    overall_total_tasks = 0
    overall_non_gradable_count = 0
    for row in rows:
        total = int(row["total_tasks"] or 0)
        pending_resident = int(row["pending_resident"] or 0)
        pending_resident2 = int(row["pending_resident2"] or 0)
        pending_arbitration = int(row["pending_arbitration"] or 0)
        non_gradable_count = int(row["non_gradable_count"] or 0)
        overall_total_tasks += total
        overall_non_gradable_count += non_gradable_count
        data.append(
            {
                "hospital_id": row["hospital_id"],
                "hospital_name": row["hospital_name"],
                "lab_unit_id": row["lab_unit_id"],
                "lab_unit_name": row["lab_unit_name"],
                "disease_id": row["disease_id"],
                "disease_name": row["disease_name"],
                "total_tasks": total,
                "pending_resident": pending_resident,
                "pending_resident_pct": _pct(pending_resident, total),
                "pending_resident2": pending_resident2,
                "pending_resident2_pct": _pct(pending_resident2, total),
                "pending_arbitration": pending_arbitration,
                "pending_arbitration_pct": _pct(pending_arbitration, total),
                "non_gradable_count": non_gradable_count,
                "non_gradable_pct": _pct(non_gradable_count, total),
            }
        )

    return jsonify(
        {
            "data": data,
            "meta": {
                "lab_unit_scope_count": len(lab_unit_ids),
                "cumulative_total_tasks": overall_total_tasks,
                "cumulative_non_gradable_count": overall_non_gradable_count,
                "cumulative_non_gradable_pct": _pct(overall_non_gradable_count, overall_total_tasks),
                "filters": {
                    "disease_id": params["disease_id"],
                    "lab_unit_id": params["lab_unit_id"],
                    "hospital_id": params["hospital_id"],
                },
            },
        }
    )


@bp.route("/api/hospital-dashboard/user-view", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def hospital_dashboard_user_view():
    lab_unit_ids = _scoped_lab_unit_ids()
    if not lab_unit_ids:
        return jsonify({"data": [], "meta": {"lab_unit_scope_count": 0}})

    filters = {
        "disease_id": _optional_int("disease_id"),
        "lab_unit_id": _optional_int("lab_unit_id"),
        "hospital_id": _optional_int("hospital_id"),
    }
    with get_db_session() as db:
        authorized_task_ids = _authorized_task_ids(db, **filters)
    params: dict[str, Any] = {
        "authorized_task_ids": authorized_task_ids or [-1],
        **filters,
    }
    query_sql = sa.text(
        """
        SELECT
            disease_id,
            disease_name,
            grader_user_id AS user_id,
            COALESCE(grader_full_name, grader_username, 'Unknown') AS user_name,
            COUNT(*)::int AS completed_count
        FROM mvw_grading_data_all
        WHERE task_id IN :authorized_task_ids
          AND grade_id IS NOT NULL
          AND grade_role_slot IN ('resident', 'resident2', 'arbitrator')
          AND (:disease_id IS NULL OR disease_id = :disease_id)
          AND (:lab_unit_id IS NULL OR lab_unit_id = :lab_unit_id)
          AND (:hospital_id IS NULL OR hospital_id = :hospital_id)
        GROUP BY disease_id, disease_name, grader_user_id, COALESCE(grader_full_name, grader_username, 'Unknown')
        ORDER BY disease_name, user_name
        """
    ).bindparams(sa.bindparam("authorized_task_ids", expanding=True))

    with get_db_session() as db:
        rows = db.execute(query_sql, params).mappings().all()

    data = [
        {
            "disease_id": row["disease_id"],
            "disease_name": row["disease_name"],
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "completed_count": int(row["completed_count"] or 0),
        }
        for row in rows
    ]
    return jsonify(
        {
            "data": data,
            "meta": {
                "lab_unit_scope_count": len(lab_unit_ids),
                "filters": {
                    "disease_id": params["disease_id"],
                    "lab_unit_id": params["lab_unit_id"],
                    "hospital_id": params["hospital_id"],
                },
            },
        }
    )


@bp.route("/api/hospital-dashboard/roster-view", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def hospital_dashboard_roster_view():
    lab_unit_ids = _scoped_lab_unit_ids()
    if not lab_unit_ids:
        return jsonify({"data": [], "meta": {"lab_unit_scope_count": 0}})

    params: dict[str, Any] = {
        "lab_unit_ids": lab_unit_ids,
        "disease_id": _optional_int("disease_id"),
        "lab_unit_id": _optional_int("lab_unit_id"),
        "hospital_id": _optional_int("hospital_id"),
    }
    query_sql = sa.text(
        """
        SELECT
            h.id AS hospital_id,
            h.name AS hospital_name,
            lu.id AS lab_unit_id,
            lu.name AS lab_unit_name,
            d.id AS disease_id,
            d.name AS disease_name,
            u.id AS user_id,
            COALESCE(u.full_name, u.username, 'Unknown') AS user_name,
            udur.can_grade_resident,
            udur.can_grade_resident2,
            udur.can_arbitrate
        FROM user_disease_unit_role udur
        JOIN users u ON u.id = udur.user_id
        JOIN diseases d ON d.id = udur.disease_id
        JOIN lab_units lu ON lu.id = udur.lab_unit_id
        LEFT JOIN hospitals h ON h.id = lu.hospital_id
        WHERE udur.active = true
          AND udur.lab_unit_id IN :lab_unit_ids
          AND (:disease_id IS NULL OR d.id = :disease_id)
          AND (:lab_unit_id IS NULL OR lu.id = :lab_unit_id)
          AND (:hospital_id IS NULL OR h.id = :hospital_id)
          AND (udur.can_grade_resident OR udur.can_grade_resident2 OR udur.can_arbitrate)
        ORDER BY h.name, lu.name, d.name, user_name
        """
    ).bindparams(sa.bindparam("lab_unit_ids", expanding=True))

    try:
        with get_db_session() as db:
            rows = db.execute(query_sql, params).mappings().all()
    except Exception as exc:
        return (
            jsonify(
                {
                    "data": [],
                    "error": f"Failed to fetch roster view: {sanitize_log_value(str(exc))}",
                }
            ),
            500,
        )

    grouped: dict[tuple[int | None, int, int], dict[str, Any]] = {}

    for row in rows:
        key = (row["hospital_id"], row["lab_unit_id"], row["disease_id"])
        entry = grouped.get(key)
        if entry is None:
            entry = {
                "hospital_id": row["hospital_id"],
                "hospital_name": row["hospital_name"],
                "lab_unit_id": row["lab_unit_id"],
                "lab_unit_name": row["lab_unit_name"],
                "disease_id": row["disease_id"],
                "disease_name": row["disease_name"],
                "resident_slot_users": [],
                "resident2_slot_users": [],
                "arbitrator_slot_users": [],
            }
            grouped[key] = entry

        user_obj = {"user_id": row["user_id"], "user_name": row["user_name"]}
        if row["can_grade_resident"] and user_obj not in entry["resident_slot_users"]:
            entry["resident_slot_users"].append(user_obj)
        if row["can_grade_resident2"] and user_obj not in entry["resident2_slot_users"]:
            entry["resident2_slot_users"].append(user_obj)
        if row["can_arbitrate"] and user_obj not in entry["arbitrator_slot_users"]:
            entry["arbitrator_slot_users"].append(user_obj)

    data = list(grouped.values())
    data.sort(
        key=lambda item: (
            item.get("hospital_name") or "",
            item.get("lab_unit_name") or "",
            item.get("disease_name") or "",
        )
    )

    return jsonify(
        {
            "data": data,
            "meta": {
                "lab_unit_scope_count": len(lab_unit_ids),
                "filters": {
                    "disease_id": params["disease_id"],
                    "lab_unit_id": params["lab_unit_id"],
                    "hospital_id": params["hospital_id"],
                },
            },
        }
    )


@bp.route("/api/hospital-dashboard/encounter-view", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def hospital_dashboard_encounter_view():
    lab_unit_ids = _scoped_lab_unit_ids()
    if not lab_unit_ids:
        return jsonify(
            {
                "data": {
                    "total_encounters": 0,
                    "verified_encounters": 0,
                    "verified_encounter_pct": 0.0,
                    "pending_direct_images": 0,
                    "ai_grades_by_disease": [],
                },
                "meta": {"lab_unit_scope_count": 0},
            }
        )

    filters = {
        "disease_id": _optional_int("disease_id"),
        "lab_unit_id": _optional_int("lab_unit_id"),
        "hospital_id": _optional_int("hospital_id"),
    }
    with get_db_session() as db:
        authorized_task_ids = _authorized_task_ids(db, **filters)
        authorized_encounter_ids = _authorized_encounter_ids(db, **filters)
        authorized_direct_upload_ids = _authorized_direct_upload_ids(db, **filters)

    params: dict[str, Any] = {
        "lab_unit_ids": lab_unit_ids,
        "authorized_task_ids": authorized_task_ids or [-1],
        "authorized_encounter_ids": authorized_encounter_ids or [-1],
        "authorized_direct_upload_ids": authorized_direct_upload_ids or [-1],
        **filters,
    }

    summary_sql = sa.text(
        """
        WITH encounter_scope AS (
            SELECT pe.id, pe.encounter_verified_status
            FROM patient_encounters pe
            LEFT JOIN lab_units lu ON lu.id = pe.lab_unit_id
            WHERE pe.id IN :authorized_encounter_ids
              AND (:disease_id IS NULL OR pe.disease_id = :disease_id)
              AND (:lab_unit_id IS NULL OR pe.lab_unit_id = :lab_unit_id)
              AND (:hospital_id IS NULL OR lu.hospital_id = :hospital_id)
        ),
        direct_scope AS (
            SELECT DISTINCT diu.id
            FROM direct_image_uploads diu
            LEFT JOIN direct_image_verifications div ON div.image_upload_id = diu.id
            WHERE diu.id IN :authorized_direct_upload_ids
              AND (:disease_id IS NULL OR diu.disease_id = :disease_id)
              AND (:lab_unit_id IS NULL OR diu.lab_unit_id = :lab_unit_id)
              AND (:hospital_id IS NULL OR diu.hospital_id = :hospital_id)
              AND (div.id IS NULL OR lower(COALESCE(div.verified_status, '')) = 'pending')
        )
        SELECT
            (SELECT COUNT(*)::int FROM encounter_scope) AS total_encounters,
            (
                SELECT COUNT(*)::int
                FROM encounter_scope es
                WHERE lower(COALESCE(es.encounter_verified_status, '')) = 'verified'
            ) AS verified_encounters,
            (SELECT COUNT(*)::int FROM direct_scope) AS pending_direct_images
        """
    ).bindparams(
        sa.bindparam("authorized_encounter_ids", expanding=True),
        sa.bindparam("authorized_direct_upload_ids", expanding=True),
    )

    ai_grades_sql = sa.text(
        """
        SELECT
            disease_id,
            disease_name,
            COUNT(*)::int AS ai_grade_count
        FROM mvw_grading_data_all
        WHERE task_id IN :authorized_task_ids
          AND grade_id IS NOT NULL
          AND grade_role_slot = 'ai'
          AND (:disease_id IS NULL OR disease_id = :disease_id)
          AND (:lab_unit_id IS NULL OR lab_unit_id = :lab_unit_id)
          AND (:hospital_id IS NULL OR hospital_id = :hospital_id)
        GROUP BY disease_id, disease_name
        ORDER BY disease_name
        """
    ).bindparams(sa.bindparam("authorized_task_ids", expanding=True))

    with get_db_session() as db:
        summary_row = db.execute(summary_sql, params).mappings().first() or {}
        ai_rows = db.execute(ai_grades_sql, params).mappings().all()

    total_encounters = int(summary_row.get("total_encounters") or 0)
    verified_encounters = int(summary_row.get("verified_encounters") or 0)
    pending_direct_images = int(summary_row.get("pending_direct_images") or 0)

    return jsonify(
        {
            "data": {
                "total_encounters": total_encounters,
                "verified_encounters": verified_encounters,
                "verified_encounter_pct": _pct(verified_encounters, total_encounters),
                "pending_direct_images": pending_direct_images,
                "ai_grades_by_disease": [
                    {
                        "disease_id": row["disease_id"],
                        "disease_name": row["disease_name"],
                        "ai_grade_count": int(row["ai_grade_count"] or 0),
                    }
                    for row in ai_rows
                ],
            },
            "meta": {
                "lab_unit_scope_count": len(lab_unit_ids),
                "filters": {
                    "disease_id": params["disease_id"],
                    "lab_unit_id": params["lab_unit_id"],
                    "hospital_id": params["hospital_id"],
                },
            },
        }
    )
