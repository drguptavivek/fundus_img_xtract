from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Tuple

from flask import render_template
from flask_login import current_user
from sqlalchemy import func

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import Disease, Grade, GradingTask, LabUnit, User
from authz.behaviors import clinical_lab_units
from tasks.lineage import valid_task_lineage


ROLE_LABELS = {
    "resident": "Resident",
    "resident2": "Resident 2",
    "arbitrator": "Arbitrator",
    "review": "Review",
    "ai": "AI",
}


def register_routes(bp) -> None:
    bp.add_url_rule("/grader-statistics", view_func=grader_statistics, methods=["GET"])


def _fetch_grade_counts(
    db,
    allowed_lab_unit_ids: Iterable[int],
    start_dt: datetime | None,
) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    """Return grouped grade counts keyed by disease/lab/user/role/model."""
    query = (
        db.query(
            Disease.id.label("disease_id"),
            Disease.name.label("disease_name"),
            LabUnit.id.label("lab_unit_id"),
            LabUnit.name.label("lab_unit_name"),
            Grade.role_slot.label("role_slot"),
            User.username.label("username"),
            User.full_name.label("full_name"),
            Grade.ai_model_name.label("ai_model_name"),
            Grade.ai_model_version.label("ai_model_version"),
            func.count(Grade.id).label("grade_count"),
        )
        .join(GradingTask, Grade.task_id == GradingTask.id)
        .join(Disease, GradingTask.disease_id == Disease.id)
        .join(LabUnit, GradingTask.lab_unit_id == LabUnit.id)
        .join(User, Grade.grader_user_id == User.id)
        .filter(
            GradingTask.lab_unit_id.in_(list(allowed_lab_unit_ids)),
            valid_task_lineage(GradingTask),
        )
        .group_by(
            Disease.id,
            Disease.name,
            LabUnit.id,
            LabUnit.name,
            Grade.role_slot,
            User.username,
            User.full_name,
            Grade.ai_model_name,
            Grade.ai_model_version,
        )
    )
    if start_dt:
        query = query.filter(Grade.created_at >= start_dt)

    rows = query.all()
    results: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        key = (
            row.disease_id,
            row.lab_unit_id,
            row.role_slot,
            row.username,
            row.full_name,
            row.ai_model_name,
            row.ai_model_version,
        )
        results[key] = {
            "disease_id": row.disease_id,
            "disease_name": row.disease_name,
            "lab_unit_id": row.lab_unit_id,
            "lab_unit_name": row.lab_unit_name,
            "role_slot": row.role_slot,
            "username": row.username,
            "full_name": row.full_name,
            "ai_model_name": row.ai_model_name,
            "ai_model_version": row.ai_model_version,
            "count": row.grade_count or 0,
        }
    return results


def _format_grader_name(row: Dict[str, Any]) -> str:
    if row.get("role_slot") == "ai":
        model_name = row.get("ai_model_name")
        model_version = row.get("ai_model_version")
        if model_name:
            return f"{model_name} {model_version}".strip()
    return row.get("full_name") or row.get("username") or "Unknown"


def _merge_counts(
    total_counts: Dict[Tuple[Any, ...], Dict[str, Any]],
    month_counts: Dict[Tuple[Any, ...], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    all_keys = set(total_counts) | set(month_counts)
    for key in all_keys:
        base = total_counts.get(key) or month_counts.get(key)
        if not base:
            continue
        role_slot = base.get("role_slot")
        rows.append(
            {
                "disease_id": base.get("disease_id"),
                "disease_name": base.get("disease_name"),
                "lab_unit_name": base.get("lab_unit_name"),
                "role_slot": role_slot,
                "role_label": ROLE_LABELS.get(role_slot, role_slot or "Unknown"),
                "grader_name": _format_grader_name(base),
                "month_count": month_counts.get(key, {}).get("count", 0),
                "total_count": total_counts.get(key, {}).get("count", 0),
            }
        )
    return rows


def _group_by_disease(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["disease_name"]].append(row)
    for disease, disease_rows in grouped.items():
        grouped[disease] = sorted(
            disease_rows,
            key=lambda r: (
                -r.get("total_count", 0),
                -r.get("month_count", 0),
                r.get("lab_unit_name") or "",
                r.get("grader_name") or "",
                r.get("role_label") or "",
            ),
        )
    return dict(grouped)


def _compute_totals(grouped: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, int]]:
    totals: Dict[str, Dict[str, int]] = {}
    for disease, rows in grouped.items():
        totals[disease] = {
            "month": sum(r["month_count"] for r in rows),
            "total": sum(r["total_count"] for r in rows),
        }
    return totals


def _fetch_grader_totals(
    db,
    allowed_lab_unit_ids: Iterable[int],
    start_dt: datetime | None,
) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    query = (
        db.query(
            User.id.label("user_id"),
            User.username.label("username"),
            User.full_name.label("full_name"),
            func.count(Grade.id).label("grade_count"),
        )
        .join(GradingTask, Grade.task_id == GradingTask.id)
        .join(User, Grade.grader_user_id == User.id)
        .filter(Grade.role_slot != "ai")
        .filter(
            GradingTask.lab_unit_id.in_(list(allowed_lab_unit_ids)),
            valid_task_lineage(GradingTask),
        )
        .group_by(User.id, User.username, User.full_name)
    )
    if start_dt:
        query = query.filter(Grade.created_at >= start_dt)

    rows = query.all()
    results: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        key = row.user_id
        results[key] = {
            "user_id": row.user_id,
            "username": row.username,
            "full_name": row.full_name,
            "count": row.grade_count or 0,
        }
    return results


def _merge_grader_totals(
    total_counts: Dict[Tuple[Any, ...], Dict[str, Any]],
    month_counts: Dict[Tuple[Any, ...], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    all_keys = set(total_counts) | set(month_counts)
    for key in all_keys:
        base = total_counts.get(key) or month_counts.get(key)
        if not base:
            continue
        rows.append(
            {
                "grader_name": _format_grader_name(base),
                "username": base.get("username"),
                "month_count": month_counts.get(key, {}).get("count", 0),
                "total_count": total_counts.get(key, {}).get("count", 0),
            }
        )
    return sorted(
        rows,
        key=lambda r: (-r.get("total_count", 0), -r.get("month_count", 0), r.get("grader_name") or ""),
    )


@roles_required(
    "ophthalmologist", "field_ophthalmologist", "local_admin", "data_manager", "admin"
)
def grader_statistics():
    """Show per-grader grade counts by disease and lab unit (monthly + cumulative)."""
    with get_db_session() as db:
        # Get allowed lab units via scoping
        lu_query = db.query(LabUnit)
        lu_query = clinical_lab_units(db, lu_query, current_user)
        allowed_lab_unit_ids = [lu.id for lu in lu_query.all()]
        
        if not allowed_lab_unit_ids:
            return render_template(
                "grading/grader_statistics.html",
                month_label="Last 30 days",
                month_start=None,
                grader_totals=[],
                human_data={},
                ai_data={},
                human_totals={},
                ai_totals={},
            )

        now_utc = datetime.now(timezone.utc)
        month_start = now_utc - timedelta(days=30)

        total_counts = _fetch_grade_counts(db, allowed_lab_unit_ids, start_dt=None)
        month_counts = _fetch_grade_counts(db, allowed_lab_unit_ids, start_dt=month_start)

        merged_rows = _merge_counts(total_counts, month_counts)
        human_rows = [row for row in merged_rows if row["role_slot"] != "ai"]
        ai_rows = [row for row in merged_rows if row["role_slot"] == "ai"]

        human_data = _group_by_disease(human_rows)
        ai_data = _group_by_disease(ai_rows)

        grader_totals = _merge_grader_totals(
            _fetch_grader_totals(db, allowed_lab_unit_ids, start_dt=None),
            _fetch_grader_totals(db, allowed_lab_unit_ids, start_dt=month_start),
        )

        return render_template(
            "grading/grader_statistics.html",
            month_label="Last 30 days",
            month_start=month_start,
            grader_totals=grader_totals,
            human_data=human_data,
            ai_data=ai_data,
            human_totals=_compute_totals(human_data),
            ai_totals=_compute_totals(ai_data),
        )
