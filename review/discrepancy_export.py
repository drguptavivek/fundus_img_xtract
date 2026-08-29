from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
from sqlalchemy import and_, or_, select, text

from auth.utils import utcnow
from authz import access_context, role_scoped_rows
from job_store import db_set_item_state, db_set_job_status
from models import (
    BASE_DIR,
    IMAGE_DIR,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    EncounterFile,
    PatientEncounters,
    DirectImageUpload,
    DIRECT_UPLOAD_DIR,
    CuratedDataset,
    CuratedDatasetItem,
    DatasetShare,
    User,
)
from data_authorization.models import ProjectRoleGrant
from project_configuration.models import ProjectLabUnit
from models import Role
from tasks.access import task_columns
from db_transaction_manager import get_db_session
from utils.fileUtils import abs_from_parts
from utils.discrepancy_filters import build_discrepancy_filter_query
from utils.final_grade_basis import (
    final_grade_basis_label,
    normalize_final_grade_basis,
    sql_final_grade_expression,
    sql_final_plus_review_expression,
)
from utils.mvw_image_listing_v2 import get_mv_name_for_disease


def authorized_export_project_grant_ids(
    db, *, actor: User, include_identifiers: bool
) -> frozenset[int]:
    """Resolve export grants with ORM; SQL consumers only receive opaque IDs."""
    role_name = "pii_exporter" if include_identifiers else "data_exporter"
    site_enabled = select(ProjectLabUnit.id).where(
        ProjectLabUnit.project_id == ProjectRoleGrant.project_id,
        ProjectLabUnit.lab_unit_id == ProjectRoleGrant.lab_unit_id,
        ProjectLabUnit.active.is_(True),
        ProjectLabUnit.sites_can_export_grades.is_(True),
    ).exists()
    return frozenset(
        db.execute(
            select(ProjectRoleGrant.id)
            .join(Role, Role.id == ProjectRoleGrant.role_id)
            .where(
                ProjectRoleGrant.user_id == actor.id,
                ProjectRoleGrant.active.is_(True),
                Role.name == role_name,
                or_(
                    ProjectRoleGrant.scope_type == "project",
                    and_(
                        ProjectRoleGrant.scope_type == "lab_unit",
                        ProjectRoleGrant.lab_unit_id.is_not(None),
                        site_enabled,
                    ),
                ),
            )
        ).scalars().all()
    )


def authorized_export_project_lab_unit_ids(
    db, *, actor: User, project_id: int, include_identifiers: bool
) -> frozenset[int]:
    """Return exact project Lab Units usable for one export action."""
    configured = frozenset(
        db.execute(
            select(ProjectLabUnit.lab_unit_id).where(
                ProjectLabUnit.project_id == project_id,
                ProjectLabUnit.active.is_(True),
            )
        ).scalars().all()
    )
    if actor.has_role("admin"):
        return configured
    grant_ids = authorized_export_project_grant_ids(
        db, actor=actor, include_identifiers=include_identifiers
    )
    if not grant_ids:
        return frozenset()
    grants = db.execute(
        select(ProjectRoleGrant.scope_type, ProjectRoleGrant.lab_unit_id).where(
            ProjectRoleGrant.id.in_(grant_ids),
            ProjectRoleGrant.project_id == project_id,
        )
    ).all()
    if any(scope_type == "project" for scope_type, _lab_id in grants):
        return configured
    return frozenset(
        lab_id
        for scope_type, lab_id in grants
        if scope_type == "lab_unit" and lab_id in configured
    )

EXPORT_DIR = BASE_DIR / "files" / "exports"
MAX_ROWS_PER_ZIP = 200
MAX_BYTES_PER_ZIP = 200 * 1024 * 1024  # 200 MB
EXPORT_RETENTION_HOURS = 24
ARTIFACT_SCOPE_FILENAME = "authorized_task_ids.json"


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
    final_plus_review: Optional[str]
    grading_details_json: str
    ai_review_comments: List[str]
    ai_review_statuses: List[str]
    image_uuid: Optional[str]
    encounter_file_id: Optional[int]
    encounter_file_uuid: Optional[str]
    encounter_filename: Optional[str]
    encounter_upload_date: Optional[datetime]
    direct_image_upload_id: Optional[int]
    direct_image_uuid: Optional[str]
    direct_filename: Optional[str]
    direct_edited_filename: Optional[str]
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
        actor_id = user_context.get("user_id") if user_context else None
        if not actor_id or filters.get("project_capability_user_id") != actor_id:
            raise PermissionError("Export actor facts are missing or inconsistent")
        with get_db_session() as db:
            actor = db.get(User, int(actor_id))
            if actor is None or not actor.is_active:
                raise PermissionError("Export actor is inactive or missing")
            filters = reauthorize_discrepancy_filters(db, actor, filters)
        _cleanup_old_exports()
        rows = _fetch_filtered_rows(filters)
        if not rows:
            db_set_job_status(job_token, "error", error="No tasks match filters")
            db_set_item_state(job_token, "discrepancy_export", "error", "No tasks match filters")
            return

        export_dir = EXPORT_DIR / job_token
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "filters.json").write_text(
            json.dumps(filters, ensure_ascii=True), encoding="utf-8"
        )
        (export_dir / ARTIFACT_SCOPE_FILENAME).write_text(
            json.dumps({"task_ids": sorted({row.task_id for row in rows})}),
            encoding="utf-8",
        )

        graded_rows = _build_task_payload(
            rows,
            include_original_filenames=bool(filters.get("include_original_filename")),
        )
        excel_path = _write_excel(graded_rows, filters, export_dir)
        _write_grading_scheme(filters.get("disease_id"), export_dir)
        include_original = bool(filters.get("include_original_filename"))
        skip_image_zips = bool(filters.get("skip_image_zips"))
        zip_paths: List[Path] = []
        warnings: List[str] = []
        if include_original:
            warnings.append("Image ZIPs skipped because include_original_filename=true")
        elif skip_image_zips:
            warnings.append("Image ZIPs skipped because skip_image_zips=true")
        else:
            zip_paths, warnings = _write_zips(graded_rows, export_dir)

        if warnings:
            (export_dir / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")

        db_set_job_status(job_token, "done")
        db_set_item_state(
            job_token,
            "discrepancy_export",
            "completed",
            f"excel={excel_path.name}; zips={','.join(p.name for p in zip_paths)}",
        )
    except Exception as exc:
        db_set_job_status(job_token, "error", error=str(exc))
        db_set_item_state(job_token, "discrepancy_export", "error", str(exc))


def reauthorize_discrepancy_filters(
    db, actor: User, requested_filters: Dict[str, Any]
) -> Dict[str, Any]:
    """Replace queued scope claims with the actor's current persisted scope."""
    from sqlalchemy import select

    from authz.behaviors import identifier_release_lab_units, role_lab_units
    from models import LabUnit

    pii_action = requested_filters.get("authorization_action") == "pii_export"
    if pii_action:
        query = identifier_release_lab_units(db, select(LabUnit), actor)
    else:
        query = role_lab_units(
            db,
            select(LabUnit),
            actor,
            lab_roles={"data_exporter", "data_manager"},
            hospital_roles={"data_manager"},
            project_roles={"data_exporter"},
            allow_admin=True,
        )
    current_lab_ids = {
        lab.id for lab in db.execute(query).scalars().unique().all()
    }
    project_id = requested_filters.get("project_id")
    if project_id is not None:
        current_lab_ids.intersection_update(
            authorized_export_project_lab_unit_ids(
                db,
                actor=actor,
                project_id=int(project_id),
                include_identifiers=pii_action,
            )
        )
    requested_lab_ids = {
        int(lab_id)
        for lab_id in requested_filters.get("allowed_lab_units", ())
        if lab_id is not None
    }
    if not requested_lab_ids or not requested_lab_ids.issubset(current_lab_ids):
        raise PermissionError("Current export scope no longer covers the queued request")
    allowed_lab_ids = requested_lab_ids

    refreshed = dict(requested_filters)
    refreshed["allowed_lab_units"] = sorted(allowed_lab_ids)
    refreshed["project_capability_user_id"] = actor.id
    refreshed["project_capability_role_names"] = [
        "pii_exporter" if pii_action else "data_exporter"
    ]
    refreshed["project_capability_grant_ids"] = sorted(
        authorized_export_project_grant_ids(
            db, actor=actor, include_identifiers=pii_action
        )
    )
    refreshed["allow_classical_capability"] = (
        actor.has_role("admin")
        if pii_action
        else actor.has_role("data_exporter", "data_manager")
    )
    if not refreshed["allow_classical_capability"] and not actor.has_role("admin"):
        # Project grants remain usable through the SQL predicate below, but a
        # queued Boolean can never preserve classical authority.
        refreshed["allow_classical_capability"] = False
    return refreshed


def reauthorize_discrepancy_artifact(
    db,
    actor: User,
    requested_filters: Dict[str, Any],
    artifact_task_ids: Sequence[int],
) -> bool:
    """Require every persisted artifact task to remain in the actor's exact scope."""
    expected = {int(task_id) for task_id in artifact_task_ids if task_id}
    if not expected:
        return False
    refreshed = reauthorize_discrepancy_filters(db, actor, requested_filters)
    probe_filters = dict(refreshed)
    probe_filters["task_ids"] = sorted(expected)
    probe_filters["randomize_selection"] = False
    probe_filters.pop("random_seed", None)
    currently_authorized = {row.task_id for row in _fetch_filtered_rows(probe_filters)}
    return currently_authorized == expected


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
        authorized_task_ids = _authorized_dataset_task_ids(
            dataset_id=dataset_id,
            metadata=metadata,
        )
        rows = _fetch_rows_by_task_ids(
            authorized_task_ids,
            metadata.get("disease_id"),
        )
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


def _authorized_dataset_task_ids(
    *,
    dataset_id: int,
    metadata: Dict[str, Any],
) -> list[int]:
    """Re-read the dataset and its exact authority inside the worker."""

    with get_db_session() as db:
        dataset = db.execute(
            select(CuratedDataset).where(
                CuratedDataset.id == dataset_id,
                CuratedDataset.is_active.is_(True),
                CuratedDataset.is_finalized.is_(True),
            )
        ).scalar_one_or_none()
        if dataset is None:
            raise PermissionError("Dataset is missing, inactive, or not finalized")

        canonical_ids = list(
            db.execute(
                select(CuratedDatasetItem.task_id).where(
                    CuratedDatasetItem.dataset_id == dataset_id,
                    CuratedDatasetItem.include_in_export.is_(True),
                )
            ).scalars()
        )
        if not canonical_ids:
            return []

        share_id = metadata.get("share_id")
        if share_id is not None:
            share = db.get(DatasetShare, int(share_id))
            if (
                share is None
                or share.dataset_id != dataset_id
                or not share.is_active
                or share.expires_at <= utcnow()
                or share.terms_accepted_at is None
            ):
                raise PermissionError("Dataset share credential is no longer valid")
            return canonical_ids

        actor_id = metadata.get("user_id")
        if actor_id is None:
            raise PermissionError("Dataset export actor is required")
        actor = db.get(User, int(actor_id))
        if actor is None or not actor.is_active:
            raise PermissionError("Dataset export actor is inactive or missing")

        query = role_scoped_rows(
            db.query(GradingTask.id).filter(GradingTask.id.in_(canonical_ids)),
            access_context(db, actor),
            task_columns(GradingTask),
            lab_roles={"local_admin", "data_manager", "data_exporter", "dataset_creator"},
            hospital_roles={"local_admin", "data_manager"},
            project_roles={"data_exporter", "dataset_creator"},
            allow_admin=True,
        )
        authorized_ids = {row[0] for row in query.all()}
        if authorized_ids != set(canonical_ids):
            raise PermissionError("Dataset contains tasks outside the actor's current scope")
        return canonical_ids


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
        mv_name, where_sql, params, _selected_ai_model_id = build_discrepancy_filter_query(db, filters)
        if not mv_name:
            return []
        final_grade_basis = normalize_final_grade_basis(filters.get("final_grade_basis"))

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
            order_clause = "ORDER BY v.task_id DESC"

        base_query = f"""
            FROM {mv_name} v
            WHERE {where_sql}
        """

        data_sql = f"""
            SELECT
                v.task_id,
                v.task_uuid,
                v.task_state,
                v.lab_unit_name,
                v.hospital_name,
                v.has_consensus,
                v.consensus_type,
                v.final_grade_name,
                v.resident_grade_name,
                v.resident_comment,
                v.resident_selected_features_json,
                v.resident2_grade_name,
                v.resident2_comment,
                v.resident2_selected_features_json,
                v.arbitrator_grade_name,
                v.arbitrator_comment,
                v.arbitrator_selected_features_json,
                v.review_grade_name,
                v.review_comment,
                v.review_selected_features_json,
                v.regrade_adj_grade_name,
                v.regrade_adj_comment,
                v.regrade_adj_selected_features_json,
                v.ai_models_json,
                {sql_final_grade_expression(final_grade_basis)} AS final_impression,
                {sql_final_plus_review_expression(final_grade_basis)} AS final_plus_review,
                v.image_uuid,
                v.encounter_file_id,
                v.encounter_file_uuid,
                v.encounter_filename,
                v.encounter_upload_date,
                v.direct_image_upload_id,
                v.direct_image_uuid,
                v.direct_filename,
                v.direct_edited_filename,
                v.direct_folder_rel,
                v.disease_name
            {base_query}
            {order_clause}
        """

        rows = db.execute(text(data_sql), params).fetchall()

        results: List[ExportTaskRow] = []
        for row in rows:
            ai_models = _parse_ai_models(row.ai_models_json)
            ai_review_comments, ai_review_statuses = _collect_ai_review_lists(ai_models)
            grading_details_json = _build_grading_details_json(row, ai_models)
            results.append(
                ExportTaskRow(
                    task_id=row.task_id,
                    task_uuid=str(row.task_uuid),
                    disease=row.disease_name,
                    lab_unit=row.lab_unit_name,
                    hospital=row.hospital_name,
                    state=row.task_state,
                    consensus_status=row.has_consensus,
                    consensus_method=row.consensus_type,
                    final_impression=row.final_impression,
                    final_plus_review=row.final_plus_review,
                    grading_details_json=grading_details_json,
                    ai_review_comments=ai_review_comments,
                    ai_review_statuses=ai_review_statuses,
                    image_uuid=row.image_uuid,
                    encounter_file_id=row.encounter_file_id,
                    encounter_file_uuid=row.encounter_file_uuid,
                    encounter_filename=row.encounter_filename,
                    encounter_upload_date=row.encounter_upload_date,
                    direct_image_upload_id=row.direct_image_upload_id,
                    direct_image_uuid=row.direct_image_uuid,
                    direct_filename=row.direct_filename,
                    direct_edited_filename=row.direct_edited_filename,
                    direct_folder_rel=row.direct_folder_rel,
                )
            )

        return results


def _parse_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _parse_ai_models(value: Any) -> Dict[str, Dict[str, Any]]:
    parsed = _parse_json_value(value)
    if isinstance(parsed, dict):
        return parsed
    return {}


def _collect_ai_review_lists(ai_models: Dict[str, Dict[str, Any]]) -> tuple[List[str], List[str]]:
    comments: List[str] = []
    statuses: List[str] = []
    for model in ai_models.values():
        comment = model.get("ai_review_comment")
        status = model.get("ai_review_status")
        if comment:
            comments.append(comment)
        if status:
            statuses.append(status)
    return comments, statuses


def _build_grading_details_json(row: Any, ai_models: Dict[str, Dict[str, Any]]) -> str:
    details: List[Dict[str, Any]] = []

    def _add_role(role: str, grade_name: Any, comment: Any, features: Any) -> None:
        if grade_name is None and comment is None and features is None:
            return
        details.append(
            {
                "role_slot": role,
                "grade_name": grade_name,
                "comment": comment,
                "selected_features": _parse_json_value(features),
            }
        )

    _add_role("resident", row.resident_grade_name, row.resident_comment, row.resident_selected_features_json)
    _add_role("resident2", row.resident2_grade_name, row.resident2_comment, row.resident2_selected_features_json)
    _add_role("arbitrator", row.arbitrator_grade_name, row.arbitrator_comment, row.arbitrator_selected_features_json)
    _add_role("review", row.review_grade_name, row.review_comment, row.review_selected_features_json)
    _add_role("regrade_adj", row.regrade_adj_grade_name, row.regrade_adj_comment, row.regrade_adj_selected_features_json)

    for key in sorted(ai_models.keys(), key=lambda k: int(k) if str(k).isdigit() else k):
        model = ai_models[key]
        details.append(
            {
                "role_slot": "ai",
                "grade_name": model.get("ai_grade_name"),
                "comment": model.get("ai_comment"),
                "selected_features": _parse_json_value(model.get("ai_selected_features")),
                "ai_model_id": model.get("ai_model_id") or (int(key) if str(key).isdigit() else None),
                "ai_model_name": model.get("ai_model_name"),
                "ai_model_version": model.get("ai_model_version"),
                "ai_probability": model.get("ai_probability"),
                "ai_review_status": model.get("ai_review_status"),
                "ai_review_comment": model.get("ai_review_comment"),
            }
        )

    return json.dumps(details, ensure_ascii=True)


def _extract_ai_probability(comment: Optional[str], provided: Optional[Any] = None) -> Optional[str]:
    if provided is not None:
        try:
            return str(provided)
        except Exception:
            return None
    if not comment:
        return None
    match = re.search(r"AI probability:\s*([0-9.]+)", comment, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _load_ai_model_meta(task_ids: Sequence[int]) -> Dict[int, Dict[str, Optional[str]]]:
    if not task_ids:
        return {}
    with get_db_session() as db:
        rows = (
            db.query(Grade.task_id, Grade.ai_model_name, Grade.ai_model_version)
            .filter(Grade.role_slot == "ai", Grade.task_id.in_(task_ids))
            .all()
        )
    meta: Dict[int, Dict[str, Optional[str]]] = {}
    for task_id, model_name, model_version in rows:
        entry = meta.setdefault(task_id, {"ai_model_name": None, "ai_model_version": None})
        if model_name and not entry["ai_model_name"]:
            entry["ai_model_name"] = model_name
        if model_version and not entry["ai_model_version"]:
            entry["ai_model_version"] = model_version
    return meta


def _format_export_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return str(value)
    except Exception:
        return None


def _load_grade_dates(task_ids: Sequence[int]) -> Dict[int, Dict[str, Optional[str]]]:
    if not task_ids:
        return {}
    roles = ("resident", "resident2", "arbitrator", "review", "regrade_adj", "ai")
    with get_db_session() as db:
        rows = (
            db.query(
                Grade.task_id,
                Grade.role_slot,
                Grade.ai_model_id,
                Grade.created_at,
                Grade.updated_at,
            )
            .filter(Grade.task_id.in_(task_ids), Grade.role_slot.in_(roles))
            .order_by(
                Grade.task_id.asc(),
                Grade.role_slot.asc(),
                Grade.ai_model_id.asc().nullsfirst(),
                Grade.created_at.desc(),
            )
            .all()
        )

    dates: Dict[int, Dict[str, Optional[str]]] = {}
    seen: set[tuple[int, str, Optional[int]]] = set()
    for task_id, role_slot, ai_model_id, created_at, updated_at in rows:
        key = (task_id, role_slot, ai_model_id if role_slot == "ai" else None)
        if key in seen:
            continue
        seen.add(key)
        grade_date = _format_export_datetime(updated_at or created_at)
        task_dates = dates.setdefault(task_id, {})
        if role_slot == "ai":
            task_dates.setdefault("ai", grade_date)
            if ai_model_id is not None:
                task_dates[f"ai:{ai_model_id}"] = grade_date
        else:
            task_dates[role_slot] = grade_date
    return dates


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
            "ai_model_id": item.get("ai_model_id"),
            "ai_model_name": item.get("ai_model_name"),
            "ai_model_version": item.get("ai_model_version"),
            "ai_probability": _extract_ai_probability(
                item.get("comment"),
                item.get("ai_probability"),
            ),
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


def _build_task_payload(
    rows: Sequence[ExportTaskRow],
    *,
    include_original_filenames: bool = False,
) -> List[Dict[str, Any]]:
    task_ids = [r.task_id for r in rows]
    ai_model_meta = _load_ai_model_meta(task_ids) if task_ids else {}
    grade_dates = _load_grade_dates(task_ids) if task_ids else {}

    data: List[Dict[str, Any]] = []
    for row in rows:
        grades = _extract_grades_by_role(row.grading_details_json)
        ai_grade = grades.get("ai", {})
        if ai_grade.get("ai_model_version") is None or ai_grade.get("ai_model_name") is None:
            meta = ai_model_meta.get(row.task_id)
            if meta:
                if not ai_grade.get("ai_model_name"):
                    ai_grade["ai_model_name"] = meta.get("ai_model_name")
                if not ai_grade.get("ai_model_version"):
                    ai_grade["ai_model_version"] = meta.get("ai_model_version")
        ai_grade["ai_review_comments"] = row.ai_review_comments
        ai_grade["ai_review_statuses"] = row.ai_review_statuses
        grades["ai"] = ai_grade
        row_grade_dates = grade_dates.get(row.task_id, {})
        ai_model_id = ai_grade.get("ai_model_id")
        ai_grade_date = row_grade_dates.get(f"ai:{ai_model_id}") if ai_model_id is not None else None
        if ai_grade_date is None:
            ai_grade_date = row_grade_dates.get("ai")

        has_review = "review" in grades
        image_uuid = row.encounter_file_uuid or row.direct_image_uuid or row.image_uuid

        file_path: Optional[Path] = None
        renamed_filename: Optional[str] = None
        if row.encounter_file_id and row.encounter_filename and row.encounter_upload_date:
            date_str = row.encounter_upload_date.strftime("%Y_%m_%d")
            file_path = (IMAGE_DIR / date_str / row.encounter_filename).resolve()
            ext = Path(row.encounter_filename).suffix.lower() or ".jpg"
            renamed_filename = f"{image_uuid}{ext}"
        elif row.direct_image_upload_id and row.direct_folder_rel:
            filename = row.direct_edited_filename or row.direct_filename
            if filename:
                if row.direct_edited_filename:
                    file_path = (DIRECT_UPLOAD_DIR / row.direct_folder_rel / "edited" / filename).resolve()
                else:
                    file_path = (DIRECT_UPLOAD_DIR / row.direct_folder_rel / filename).resolve()
                ext = Path(filename).suffix.lower() or ".jpg"
                renamed_filename = f"{image_uuid}{ext}"

        payload = {
                "task_id": row.task_id,
                "task_uuid": row.task_uuid,
                "disease": row.disease,
                "hospital": row.hospital,
                "lab_unit": row.lab_unit,
                "state": row.state,
                "consensus_status": row.consensus_status,
                "consensus_method": row.consensus_method,
                "final_impression": row.final_impression,
                "final_plus_review": row.final_plus_review,
                "has_review": "yes" if has_review else "no",
                "resident_grade": grades.get("resident", {}).get("impression"),
                "resident_grade_date": row_grade_dates.get("resident"),
                "resident_comment": grades.get("resident", {}).get("comment"),
                "resident_features_json": _serialize_features_json(
                    grades.get("resident", {}).get("selected_features")
                ),
                "resident2_grade": grades.get("resident2", {}).get("impression"),
                "resident2_grade_date": row_grade_dates.get("resident2"),
                "resident2_comment": grades.get("resident2", {}).get("comment"),
                "resident2_features_json": _serialize_features_json(
                    grades.get("resident2", {}).get("selected_features")
                ),
                "arbitrator_grade": grades.get("arbitrator", {}).get("impression"),
                "arbitrator_grade_date": row_grade_dates.get("arbitrator"),
                "arbitrator_comment": grades.get("arbitrator", {}).get("comment"),
                "arbitrator_features_json": _serialize_features_json(
                    grades.get("arbitrator", {}).get("selected_features")
                ),
                "review_grade": grades.get("review", {}).get("impression"),
                "review_grade_date": row_grade_dates.get("review"),
                "review_comment": grades.get("review", {}).get("comment"),
                "review_features_json": _serialize_features_json(
                    grades.get("review", {}).get("selected_features")
                ),
                "regrade_adj_grade": grades.get("regrade_adj", {}).get("impression"),
                "regrade_adj_grade_date": row_grade_dates.get("regrade_adj"),
                "regrade_adj_comment": grades.get("regrade_adj", {}).get("comment"),
                "regrade_adj_features_json": _serialize_features_json(
                    grades.get("regrade_adj", {}).get("selected_features")
                ),
                "ai_grade": ai_grade.get("impression"),
                "ai_grade_date": ai_grade_date,
                "ai_model_name": ai_grade.get("ai_model_name"),
                "ai_model_version": ai_grade.get("ai_model_version"),
                "ai_probability": ai_grade.get("ai_probability"),
                "ai_review_statuses": "; ".join(ai_grade.get("ai_review_statuses") or []),
                "ai_review_comments": "; ".join(ai_grade.get("ai_review_comments") or []),
                "image_uuid": image_uuid,
                "image_filename": renamed_filename,
                "image_path": file_path,
            }
        if include_original_filenames:
            payload["original_upload_filename"] = row.encounter_filename or row.direct_filename
        data.append(payload)
    return data


def _fetch_rows_by_task_ids(
    task_ids: Sequence[int],
    disease_id: Optional[int] = None,
    final_grade_basis: Optional[str] = None,
) -> List[ExportTaskRow]:
    """Fetch tasks by explicit ids for dataset export."""
    with get_db_session() as db:
        if not task_ids:
            return []
        final_grade_basis = normalize_final_grade_basis(final_grade_basis)

        # Use provided disease_id to pick MV columns; dataset is disease-specific
        if disease_id is None:
            disease_id = (
                db.query(GradingTask.disease_id).filter(GradingTask.id.in_(task_ids)).limit(1).scalar()
            )

        mv_name = get_mv_name_for_disease(db, disease_id)

        params: Dict[str, Any] = {"task_ids": list(task_ids)}

        base_query = f"""
            FROM {mv_name} v
            WHERE v.task_id = ANY(:task_ids)
        """

        data_sql = f"""
            SELECT
                v.task_id,
                v.task_uuid,
                v.task_state,
                v.lab_unit_name,
                v.hospital_name,
                v.has_consensus,
                v.consensus_type,
                v.final_grade_name,
                v.resident_grade_name,
                v.resident_comment,
                v.resident_selected_features_json,
                v.resident2_grade_name,
                v.resident2_comment,
                v.resident2_selected_features_json,
                v.arbitrator_grade_name,
                v.arbitrator_comment,
                v.arbitrator_selected_features_json,
                v.review_grade_name,
                v.review_comment,
                v.review_selected_features_json,
                v.regrade_adj_grade_name,
                v.regrade_adj_comment,
                v.regrade_adj_selected_features_json,
                v.ai_models_json,
                {sql_final_grade_expression(final_grade_basis)} AS final_impression,
                {sql_final_plus_review_expression(final_grade_basis)} AS final_plus_review,
                v.image_uuid,
                v.encounter_file_id,
                v.encounter_file_uuid,
                v.encounter_filename,
                v.encounter_upload_date,
                v.direct_image_upload_id,
                v.direct_image_uuid,
                v.direct_filename,
                v.direct_edited_filename,
                v.direct_folder_rel,
                v.disease_name
            {base_query}
        """

        rows = db.execute(text(data_sql), params).fetchall()

        results: List[ExportTaskRow] = []
        for row in rows:
            ai_models = _parse_ai_models(row.ai_models_json)
            ai_review_comments, ai_review_statuses = _collect_ai_review_lists(ai_models)
            grading_details_json = _build_grading_details_json(row, ai_models)
            results.append(
                ExportTaskRow(
                    task_id=row.task_id,
                    task_uuid=str(row.task_uuid),
                    disease=row.disease_name,
                    lab_unit=row.lab_unit_name,
                    hospital=row.hospital_name,
                    state=row.task_state,
                    consensus_status=row.has_consensus,
                    consensus_method=row.consensus_type,
                    final_impression=row.final_impression,
                    final_plus_review=row.final_plus_review,
                    grading_details_json=grading_details_json,
                    ai_review_comments=ai_review_comments,
                    ai_review_statuses=ai_review_statuses,
                    image_uuid=row.image_uuid,
                    encounter_file_id=row.encounter_file_id,
                    encounter_file_uuid=row.encounter_file_uuid,
                    encounter_filename=row.encounter_filename,
                    encounter_upload_date=row.encounter_upload_date,
                    direct_image_upload_id=row.direct_image_upload_id,
                    direct_image_uuid=row.direct_image_uuid,
                    direct_filename=row.direct_filename,
                    direct_edited_filename=row.direct_edited_filename,
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
    basis_row = pd.DataFrame(
        [{"filter": "final_grade_basis_label", "value": final_grade_basis_label(filters.get("final_grade_basis"))}]
    )
    filters_df = pd.concat([filters_df, basis_row], ignore_index=True)
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
