"""Field staff read and action surface, scoped to one project at a time."""
from __future__ import annotations

import logging
from datetime import date

from flask import url_for
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from models import Disease, EncounterSetImage, PatientEncounters, User
from remote_inference.encounter_service import create_manual_job
from remote_inference.manual_service import project_allows_manual_wadhwani
from remote_inference.models import ProjectEncounterAIWorkflow
from services.encounter_set_ai_inference import enqueue_wadhwani_for_task_ids
from utils.log_sanitize import sanitize_log_value

from . import audit as field_audit
from . import cache as field_cache
from .dto import (
    SOURCE_IITK,
    SOURCE_REMIDIO,
    FieldEncounterDateDTO,
    FieldEncounterDetailDTO,
    FieldEncounterRowDTO,
    FieldImageDTO,
    FieldProjectDTO,
)
from .exceptions import FieldConflict, FieldNotFound
from .policy import (
    can_request_inference,
    can_trigger_fetch,
    encounter_scope_clause,
    list_field_projects,
    resolve_project_scope,
)
from .sources import configured_sources, get_adapter
from .status import dr_dme_statuses, glaucoma_status, remidio_report

logger = logging.getLogger("field_workbench.service")

MAX_QUEUE_ROWS = 300


def _source_of(encounter: PatientEncounters) -> str:
    metadata = encounter.metadata_json if isinstance(encounter.metadata_json, dict) else {}
    upload = metadata.get("upload") if isinstance(metadata.get("upload"), dict) else {}
    return SOURCE_IITK if upload.get("source_kind") == "iitk_api" else SOURCE_REMIDIO


def _dr_dme_enabled(db, project_id: int) -> bool:
    return db.execute(
        select(ProjectEncounterAIWorkflow.id).where(
            ProjectEncounterAIWorkflow.project_id == project_id,
            ProjectEncounterAIWorkflow.workflow_key == "dr_dme",
            ProjectEncounterAIWorkflow.active.is_(True),
            ProjectEncounterAIWorkflow.manual_enabled.is_(True),
        )
    ).scalar_one_or_none() is not None


def _ai_workflows(db, project_id: int) -> tuple[str, ...]:
    out = []
    if _dr_dme_enabled(db, project_id):
        out.extend(("dr", "dme"))
    if project_allows_manual_wadhwani(db, project_id):
        out.append("glaucoma")
    return tuple(out)


def _scope_fingerprint(scope) -> str:
    return field_cache.scope_fingerprint(scope.role_names, scope.lab_unit_ids, scope.hospital_ids)


def list_projects(db, *, user) -> list[FieldProjectDTO]:
    """Projects this user may work in, each with its resolved AI policy."""
    out = []
    for project, scope in list_field_projects(db, user=user):
        out.append(
            FieldProjectDTO(
                id=project.id,
                title=project.title,
                code=project.code,
                active=project.active,
                roles=tuple(sorted(scope.role_names)),
                ai_workflows=_ai_workflows(db, project.id),
                sources=tuple(configured_sources(db, project.id)),
                can_request_inference=can_request_inference(scope),
                can_trigger_fetch=can_trigger_fetch(scope),
            )
        )
    return out


def list_encounter_dates(db, *, user, project_id: int) -> list[FieldEncounterDateDTO]:
    _, scope = resolve_project_scope(db, user=user, project_id=project_id)
    rows = db.execute(
        select(PatientEncounters.capture_date_dt, func.count(PatientEncounters.id))
        .where(
            PatientEncounters.project_id == project_id,
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.capture_date_dt.isnot(None),
            encounter_scope_clause(scope),
        )
        .group_by(PatientEncounters.capture_date_dt)
        .order_by(PatientEncounters.capture_date_dt.desc())
        .limit(180)
    ).all()
    return [FieldEncounterDateDTO(date=value.isoformat(), count=count) for value, count in rows]


def _encounter_query(db, *, project_id: int, scope):
    return (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.lab_unit),
            selectinload(PatientEncounters.encounter_set_images),
            selectinload(PatientEncounters.encounter_set_attachments),
        )
        .filter(
            PatientEncounters.project_id == project_id,
            PatientEncounters.is_set_based.is_(True),
            encounter_scope_clause(scope),
        )
    )


def _report_url(encounter: PatientEncounters) -> str:
    return url_for("mobile_api.field_encounter_report", encounter_uuid=encounter.uuid)


def _ai_for(db, encounter: PatientEncounters, *, source: str, project_id: int):
    # IITK has no AI models configured, so those encounters legitimately carry no
    # inference at all. The client renders an encounter without an AI section
    # rather than treating the absence as an error.
    if source == SOURCE_IITK:
        return ()
    statuses = list(dr_dme_statuses(db, encounter, workflow_enabled=_dr_dme_enabled(db, project_id)))
    statuses.append(
        glaucoma_status(
            db, encounter, workflow_enabled=project_allows_manual_wadhwani(db, project_id)
        )
    )
    return tuple(statuses)


def list_daily_encounters(db, *, user, project_id: int, date_value: str) -> list[FieldEncounterRowDTO]:
    """The queue for one capture date.

    The date is a plain calendar day supplied by the client, so the boundary
    matches the field user's own day without the server guessing a timezone.
    """
    _, scope = resolve_project_scope(db, user=user, project_id=project_id)
    try:
        parsed = date.fromisoformat(date_value)
    except (TypeError, ValueError) as exc:
        raise FieldConflict("date must be an ISO date (YYYY-MM-DD).", code="invalid_date") from exc

    cache_key = field_cache.queue_cache_key(
        project_id=project_id,
        date_value=parsed.isoformat(),
        user_id=user.id,
        scope_fp=_scope_fingerprint(scope),
    )
    cached = field_cache.get_cached(cache_key)
    if cached is not None:
        return cached

    encounters = (
        _encounter_query(db, project_id=project_id, scope=scope)
        .filter(PatientEncounters.capture_date_dt == parsed)
        .order_by(PatientEncounters.id.desc())
        .limit(MAX_QUEUE_ROWS)
        .all()
    )

    rows = []
    for encounter in encounters:
        source = _source_of(encounter)
        rows.append(
            FieldEncounterRowDTO(
                uuid=encounter.uuid,
                source=source,
                patient_id=encounter.patient_id,
                patient_name=encounter.name,
                capture_date=encounter.capture_date_dt.isoformat() if encounter.capture_date_dt else None,
                lab_unit=encounter.lab_unit.name if encounter.lab_unit else None,
                image_count=len(encounter.encounter_set_images or []),
                verified_status=encounter.encounter_verified_status,
                ai=_ai_for(db, encounter, source=source, project_id=project_id),
                report=None if source == SOURCE_IITK else remidio_report(
                    encounter, pdf_url=_report_url(encounter)
                ),
            )
        )

    payload = [row.to_dict() for row in rows]
    field_cache.set_cached(cache_key, payload, field_cache.QUEUE_TTL_SECONDS)
    field_audit.record(
        db,
        user_id=user.id,
        operation_type=field_audit.OPERATION_QUEUE_READ,
        request_details={"project_id": project_id, "date": parsed.isoformat()},
        result_details={"encounter_count": len(payload)},
    )
    return payload


def load_encounter(db, *, user, encounter_uuid: str):
    encounter = db.execute(
        select(PatientEncounters)
        .options(
            selectinload(PatientEncounters.lab_unit),
            selectinload(PatientEncounters.encounter_set_images),
            selectinload(PatientEncounters.encounter_set_attachments),
        )
        .where(PatientEncounters.uuid == encounter_uuid)
    ).scalar_one_or_none()
    if encounter is None or encounter.project_id is None:
        raise FieldNotFound("Encounter not found.")
    _, scope = resolve_project_scope(db, user=user, project_id=encounter.project_id)

    # Re-check the encounter itself: a project grant scoped to one lab unit must
    # not read another lab's encounters inside the same project.
    allowed = (
        _encounter_query(db, project_id=encounter.project_id, scope=scope)
        .filter(PatientEncounters.id == encounter.id)
        .first()
    )
    if allowed is None:
        raise FieldNotFound("Encounter not found.")
    return encounter, scope


def get_encounter_detail(db, *, user, encounter_uuid: str) -> dict:
    encounter, scope = load_encounter(db, user=user, encounter_uuid=encounter_uuid)
    cache_key = field_cache.detail_cache_key(
        encounter_id=encounter.id,
        project_id=encounter.project_id,
        user_id=user.id,
        scope_fp=_scope_fingerprint(scope),
    )
    cached = field_cache.get_cached(cache_key)
    if cached is not None:
        return cached

    source = _source_of(encounter)
    metadata = encounter.metadata_json if isinstance(encounter.metadata_json, dict) else {}
    patient = metadata.get("patient") if isinstance(metadata.get("patient"), dict) else {}

    images = []
    for image in sorted(encounter.encounter_set_images or [], key=lambda row: (row.spatial_position, row.id)):
        if image.asset_kind != "clinical_image":
            continue
        image_metadata = image.metadata_json if isinstance(image.metadata_json, dict) else {}
        images.append(
            FieldImageDTO(
                uuid=image.uuid,
                position=image.spatial_position,
                eye=image_metadata.get("laterality") or image_metadata.get("eye"),
                focus=image_metadata.get("focus") or image_metadata.get("centering"),
                gaze_position=image_metadata.get("gaze_position"),
                is_not_gradable=bool(image.is_not_gradable),
                thumbnail_url=url_for(
                    "mobile_api.field_encounter_image_thumbnail",
                    encounter_uuid=encounter.uuid,
                    image_uuid=image.uuid,
                ),
                image_url=url_for(
                    "mobile_api.field_encounter_image",
                    encounter_uuid=encounter.uuid,
                    image_uuid=image.uuid,
                ),
            )
        )

    detail = FieldEncounterDetailDTO(
        uuid=encounter.uuid,
        source=source,
        project_id=encounter.project_id,
        patient_id=encounter.patient_id,
        patient_name=encounter.name,
        patient_age=str(patient.get("patient_age_yrs")) if patient.get("patient_age_yrs") else None,
        patient_sex=patient.get("sex"),
        capture_date=encounter.capture_date_dt.isoformat() if encounter.capture_date_dt else None,
        lab_unit=encounter.lab_unit.name if encounter.lab_unit else None,
        verified_status=encounter.encounter_verified_status,
        referral_suggestion=encounter.referral_suggestion,
        images=tuple(images),
        ai=_ai_for(db, encounter, source=source, project_id=encounter.project_id),
        report=None if source == SOURCE_IITK else remidio_report(
            encounter, pdf_url=_report_url(encounter)
        ),
    )
    payload = detail.to_dict()
    field_cache.set_cached(cache_key, payload, field_cache.DETAIL_TTL_SECONDS)
    field_audit.record(
        db,
        user_id=user.id,
        operation_type=field_audit.OPERATION_DETAIL_READ,
        request_details={"encounter_uuid": encounter.uuid, "project_id": encounter.project_id},
    )
    return payload


def request_inference(db, *, user, encounter_uuid: str, workflows: list[str], remote_addr: str | None) -> dict:
    """Request WAI inference, gated by project policy and idempotent by design."""
    encounter, scope = load_encounter(db, user=user, encounter_uuid=encounter_uuid)
    if not can_request_inference(scope):
        raise FieldConflict("You may not request inference in this project.", code="forbidden")

    source = _source_of(encounter)
    if source == SOURCE_IITK:
        raise FieldConflict(
            "IITK encounters have no AI model configured.", code="no_ai_configured"
        )

    project_id = encounter.project_id
    requested = [item.strip().lower() for item in workflows if item and item.strip()]
    if not requested:
        requested = ["dr_dme", "glaucoma"]

    results: dict[str, dict] = {}
    for workflow in requested:
        if workflow == "dr_dme":
            results["dr_dme"] = _request_dr_dme(db, encounter, user=user, remote_addr=remote_addr)
        elif workflow == "glaucoma":
            results["glaucoma"] = _request_glaucoma(db, encounter, user=user, remote_addr=remote_addr)
        else:
            raise FieldConflict(f"Unknown workflow '{workflow}'.", code="unknown_workflow")

    # Flip the client's next poll to the new state immediately rather than
    # waiting out the cache TTL.
    field_cache.bump_encounter(encounter.id, project_id)
    post_commit = [
        result.pop("_post_commit")
        for result in results.values()
        if result.get("_post_commit")
    ]
    field_audit.record(
        db,
        user_id=user.id,
        operation_type=field_audit.OPERATION_INFERENCE_REQUEST,
        request_details={"encounter_uuid": encounter.uuid, "workflows": requested},
        result_details={
            workflow: {"queued": bool(outcome.get("queued")), "reason": outcome.get("reason")}
            for workflow, outcome in results.items()
        },
    )
    return {
        "encounter_uuid": encounter.uuid,
        "workflows": results,
        "_post_commit": post_commit,
    }


def _request_dr_dme(db, encounter: PatientEncounters, *, user, remote_addr: str | None) -> dict:
    if not _dr_dme_enabled(db, encounter.project_id):
        return {"queued": False, "reason": "workflow_disabled"}

    statuses = dr_dme_statuses(db, encounter, workflow_enabled=True)
    if not any(status.requestable for status in statuses):
        return {"queued": False, "reason": "already_present", "run_status": statuses[0].run_status}

    result = create_manual_job(
        encounter_ids=[encounter.id],
        project_id=encounter.project_id,
        user=user,
        remote_addr=remote_addr,
    )
    if not result.success:
        raise FieldConflict(result.message, code="inference_rejected")
    return {"queued": True, "job_token": (result.payload or {}).get("job_token")}


def _request_glaucoma(db, encounter: PatientEncounters, *, user, remote_addr: str | None) -> dict:
    if not project_allows_manual_wadhwani(db, encounter.project_id):
        return {"queued": False, "reason": "workflow_disabled"}

    status = glaucoma_status(db, encounter, workflow_enabled=True)
    if not status.requestable:
        return {"queued": False, "reason": "already_present", "run_status": status.run_status}

    glaucoma = db.execute(
        select(Disease).where(func.lower(Disease.name) == "glaucoma")
    ).scalars().first()
    if glaucoma is None:
        return {"queued": False, "reason": "workflow_disabled"}

    task_ids = _create_or_reuse_glaucoma_tasks(db, encounter, disease_id=glaucoma.id)
    if not task_ids:
        return {"queued": False, "reason": "no_eligible_images"}

    def _dispatch():
        # Enqueued after the caller commits: the worker reads these tasks by id,
        # so it must not start before they are visible.
        return enqueue_wadhwani_for_task_ids(
            task_ids,
            user_id=user.id,
            username=user.username,
            remote_addr=remote_addr,
            lab_unit_id=encounter.lab_unit_id,
            project_id=encounter.project_id,
            upload_profile_id=encounter.upload_profile_id,
        )

    return {"queued": True, "task_count": len(task_ids), "_post_commit": _dispatch}


def _create_or_reuse_glaucoma_tasks(db, encounter: PatientEncounters, *, disease_id: int) -> list[int]:
    """Mirror the manual workbench's task shape so both paths reuse one task."""
    from models import GradingTask

    if not encounter.lab_unit_id:
        return []
    task_ids: list[int] = []
    for image in sorted(encounter.encounter_set_images or [], key=lambda row: (row.spatial_position, row.id)):
        if (
            image.asset_kind != "clinical_image"
            or not image.creates_task
            or not image.visible_to_grader
            or image.is_not_gradable
        ):
            continue
        task = (
            db.query(GradingTask)
            .filter(
                GradingTask.encounter_set_image_id == image.id,
                GradingTask.disease_id == disease_id,
            )
            .first()
        )
        if task is None:
            task = GradingTask(
                encounter_set_image_id=image.id,
                disease_id=disease_id,
                lab_unit_id=encounter.lab_unit_id,
                source_upload_profile_id=encounter.upload_profile_id,
                grading_target_level="image",
                task_source="encounter_set_ai_inference",
            )
            db.add(task)
            db.flush()
        task_ids.append(task.id)
    return task_ids


def get_fetch_status(db, *, user, project_id: int, source: str | None) -> list[dict]:
    _, scope = resolve_project_scope(db, user=user, project_id=project_id)
    names = [source] if source else configured_sources(db, project_id) or [SOURCE_REMIDIO, SOURCE_IITK]
    out = []
    for name in names:
        try:
            adapter = get_adapter(name)
        except KeyError as exc:
            raise FieldConflict(f"Unknown source '{name}'.", code="unknown_source") from exc
        out.append(adapter.fetch_status(db, project_id=project_id, scope=scope).to_dict())
    return out


def queue_fetch(db, *, user, project_id: int, source: str, remote_addr: str | None) -> dict:
    _, scope = resolve_project_scope(db, user=user, project_id=project_id)
    if not can_trigger_fetch(scope):
        raise FieldConflict("You may not trigger a fetch in this project.", code="forbidden")
    try:
        adapter = get_adapter(source)
    except KeyError as exc:
        raise FieldConflict(f"Unknown source '{source}'.", code="unknown_source") from exc

    action_name = "queue"
    status = adapter.queue_fetch(
        db, project_id=project_id, user=user, scope=scope, remote_addr=remote_addr
    )
    field_cache.bump_project(project_id)
    logger.info(
        "Field fetch requested project_id=%s source=%s user_id=%s running=%s",
        sanitize_log_value(project_id),
        sanitize_log_value(source),
        sanitize_log_value(user.id),
        sanitize_log_value(status.running),
    )
    field_audit.record(
        db,
        user_id=user.id,
        operation_type=field_audit.OPERATION_FETCH_REQUEST,
        request_details={"project_id": project_id, "source": source, "action": action_name},
        result_details={"running": status.running, "state": status.state},
    )
    payload = status.to_dict()
    payload["_post_commit"] = status.deferred_dispatch
    return payload


def retry_fetch(db, *, user, project_id: int, source: str, remote_addr: str | None) -> dict:
    _, scope = resolve_project_scope(db, user=user, project_id=project_id)
    if not can_trigger_fetch(scope):
        raise FieldConflict("You may not trigger a fetch in this project.", code="forbidden")
    try:
        adapter = get_adapter(source)
    except KeyError as exc:
        raise FieldConflict(f"Unknown source '{source}'.", code="unknown_source") from exc

    action_name = "retry"
    status = adapter.retry_fetch(
        db, project_id=project_id, user=user, scope=scope, remote_addr=remote_addr
    )
    field_cache.bump_project(project_id)
    field_audit.record(
        db,
        user_id=user.id,
        operation_type=field_audit.OPERATION_FETCH_REQUEST,
        request_details={"project_id": project_id, "source": source, "action": action_name},
        result_details={"running": status.running, "state": status.state},
    )
    payload = status.to_dict()
    payload["_post_commit"] = status.deferred_dispatch
    return payload
