"""Use cases for configuring and pulling Remidio API data."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import (
    Camera,
    Disease,
    Job,
    JobItem,
    LabUnit,
    Project,
    RemidioConnection,
    RemidioRoutingRule,
    RemidioSite,
)
from upload_profiles.service import manager_lab_unit_ids
from utils.encryption import decrypt_password_with_salt, encrypt_password_with_salt, generate_salt
from utils.log_sanitize import sanitize_log_value

from .client import RemidioClient
from .errors import RemidioConfigError
from .ingest import ingest_staged_files
from .models import ProjectUploadProfileRemidioApiBinding, RemidioApiRoutingProfile
from .persistence import upsert_exam_payloads, upsert_sites
from .schemas import RemidioExamPayload, RemidioSecrets, UpsertSummary
from .validation import (
    extract_exam_payloads,
    extract_sites,
    normalize_date,
    normalize_device_type,
    require_gateway_ok,
    require_list_data,
)


DEFAULT_BASE_URL = "https://remidio-backend-india.appspot.com"
DEFAULT_CLIENT_NAME = "PACS_GATEWAY"
REMIDIO_API_SYNC_TASK_NAME = "celery_tasks.tasks.remidio_tasks.run_remidio_api_routing_profile_sync_task"
REMIDIO_API_SYNC_ITEM_SOURCE = "remidio_api_routing_profile"


def list_connections(db: Session, *, project_id: int | None = None) -> list[dict[str, Any]]:
    query = db.query(RemidioConnection).options(selectinload(RemidioConnection.sites))
    if project_id is not None:
        query = query.filter(RemidioConnection.project_id == project_id)
    return [_connection_summary(row) for row in query.order_by(RemidioConnection.id).all()]


def create_connection(db: Session, payload: dict[str, Any]) -> RemidioConnection:
    name = _required_string(payload, "name")
    project_id = _optional_int(payload.get("project_id"))
    if project_id is not None:
        _require_row(db, Project, project_id, "project_id")

    salt = generate_salt()
    connection = RemidioConnection(
        name=name,
        project_id=project_id,
        base_url=_normalize_base_url(payload.get("base_url") or DEFAULT_BASE_URL),
        client_name=(payload.get("client_name") or DEFAULT_CLIENT_NAME).strip(),
        client_identification_token_encrypted=encrypt_password_with_salt(
            _required_string(payload, "client_identification_token"),
            salt,
        ),
        email_encrypted=encrypt_password_with_salt(_required_string(payload, "email"), salt),
        password_encrypted=encrypt_password_with_salt(_required_string(payload, "password"), salt),
        secret_salt=salt,
        active=_optional_bool(payload.get("active"), default=True),
    )
    db.add(connection)
    db.flush()
    return connection


def patch_connection(db: Session, connection_id: int, payload: dict[str, Any]) -> RemidioConnection:
    connection = _get_connection(db, connection_id)
    if "name" in payload:
        connection.name = _required_string(payload, "name")
    if "project_id" in payload:
        project_id = _optional_int(payload.get("project_id"))
        if project_id is not None:
            _require_row(db, Project, project_id, "project_id")
        connection.project_id = project_id
    if "base_url" in payload:
        connection.base_url = _normalize_base_url(payload.get("base_url") or DEFAULT_BASE_URL)
    if "client_name" in payload:
        connection.client_name = _required_string(payload, "client_name")
    if "client_identification_token" in payload and _has_value(payload.get("client_identification_token")):
        connection.client_identification_token_encrypted = encrypt_password_with_salt(
            _required_string(payload, "client_identification_token"),
            connection.secret_salt,
        )
    if "email" in payload and _has_value(payload.get("email")):
        connection.email_encrypted = encrypt_password_with_salt(_required_string(payload, "email"), connection.secret_salt)
    if "password" in payload and _has_value(payload.get("password")):
        connection.password_encrypted = encrypt_password_with_salt(_required_string(payload, "password"), connection.secret_salt)
    if "active" in payload:
        connection.active = _optional_bool(payload.get("active"), default=True)
    connection.updated_at = utcnow()
    db.flush()
    return connection


def refresh_token(db: Session, connection_id: int) -> dict[str, Any]:
    connection = _get_connection(db, connection_id)
    client = RemidioClient(_secrets(connection))
    client.login()
    connection.last_login_at = utcnow()
    client.get_auth_token()
    connection.last_auth_token_at = utcnow()
    connection.updated_at = utcnow()
    db.flush()
    return _connection_summary(connection)


def sync_sites(db: Session, connection_id: int) -> dict[str, Any]:
    connection = _get_connection(db, connection_id)
    body = RemidioClient(_secrets(connection)).get_sites()
    sites = extract_sites(body)
    rows = upsert_sites(db, connection_id=connection.id, sites=sites)
    connection.last_auth_token_at = utcnow()
    connection.updated_at = utcnow()
    db.flush()
    return {"connection": _connection_summary(connection), "sites": [_site_summary(row) for row in rows]}


def list_sites(db: Session, connection_id: int) -> list[dict[str, Any]]:
    _get_connection(db, connection_id)
    rows = (
        db.query(RemidioSite)
        .filter(RemidioSite.remidio_connection_id == connection_id)
        .order_by(RemidioSite.site_name, RemidioSite.id)
        .all()
    )
    return [_site_summary(row) for row in rows]


def patch_site(db: Session, site_id: int, payload: dict[str, Any]) -> RemidioSite:
    site = db.get(RemidioSite, site_id)
    if site is None:
        raise RemidioConfigError("Remidio site was not found.")
    if "site_custom_identifier" in payload:
        value = payload.get("site_custom_identifier")
        site.site_custom_identifier = str(value).strip() if value not in {None, ""} else None
    if "active" in payload:
        site.active = _optional_bool(payload.get("active"), default=True)
    site.updated_at = utcnow()
    db.flush()
    return site


def list_routing_rules(db: Session, *, connection_id: int | None = None, project_id: int | None = None) -> list[dict[str, Any]]:
    query = db.query(RemidioRoutingRule).options(
        selectinload(RemidioRoutingRule.site),
        selectinload(RemidioRoutingRule.project),
        selectinload(RemidioRoutingRule.lab_unit),
        selectinload(RemidioRoutingRule.camera),
        selectinload(RemidioRoutingRule.default_disease),
    )
    if connection_id is not None:
        query = query.filter(RemidioRoutingRule.remidio_connection_id == connection_id)
    if project_id is not None:
        query = query.filter(RemidioRoutingRule.project_id == project_id)
    return [_routing_rule_summary(row) for row in query.order_by(RemidioRoutingRule.id).all()]


def upsert_routing_rule(db: Session, payload: dict[str, Any]) -> RemidioRoutingRule:
    connection_id = _required_int(payload, "remidio_connection_id")
    _get_connection(db, connection_id)
    site_id = _optional_int(payload.get("remidio_site_id"))
    site = None
    if site_id is not None:
        site = db.get(RemidioSite, site_id)
        if site is None or site.remidio_connection_id != connection_id:
            raise RemidioConfigError("remidio_site_id does not belong to the connection.")

    site_custom_identifier = ((site.site_custom_identifier if site else None) or payload.get("site_custom_identifier") or "").strip()
    if not site_custom_identifier:
        raise RemidioConfigError("site_custom_identifier is required.")
    device_type = normalize_device_type(_required_string(payload, "remidio_device_type"))

    project_id = _required_int(payload, "project_id")
    lab_unit_id = _required_int(payload, "lab_unit_id")
    camera_id = _required_int(payload, "camera_id")
    default_disease_id = _optional_int(payload.get("default_disease_id"))
    _require_row(db, Project, project_id, "project_id")
    _require_row(db, LabUnit, lab_unit_id, "lab_unit_id")
    _require_row(db, Camera, camera_id, "camera_id")
    if default_disease_id is not None:
        _require_row(db, Disease, default_disease_id, "default_disease_id")

    rule = (
        db.query(RemidioRoutingRule)
        .filter(
            RemidioRoutingRule.remidio_connection_id == connection_id,
            RemidioRoutingRule.site_custom_identifier == site_custom_identifier,
            RemidioRoutingRule.remidio_device_type == device_type,
            RemidioRoutingRule.project_id == project_id,
            RemidioRoutingRule.lab_unit_id == lab_unit_id,
            RemidioRoutingRule.camera_id == camera_id,
        )
        .one_or_none()
    )
    if rule is None:
        rule = RemidioRoutingRule(
            remidio_connection_id=connection_id,
            site_custom_identifier=site_custom_identifier,
            remidio_device_type=device_type,
            project_id=project_id,
            lab_unit_id=lab_unit_id,
            camera_id=camera_id,
        )
        db.add(rule)
    rule.remidio_site_id = site_id
    rule.default_disease_id = default_disease_id
    rule.active = _optional_bool(payload.get("active"), default=True)
    rule.updated_at = utcnow()
    db.flush()
    return rule


def pull_exams_by_date(db: Session, connection_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    connection = _get_connection(db, connection_id)
    start_date = normalize_date(_required_string(payload, "start_date"))
    end_date = normalize_date(_required_string(payload, "end_date"))
    site_custom_identifier = _required_string(payload, "site_custom_identifier")
    dry_run = bool(payload.get("dry_run", False))

    body = RemidioClient(_secrets(connection)).get_exams_by_date(
        start_date=start_date,
        end_date=end_date,
        site_custom_identifier=site_custom_identifier,
        include_file_paths=True,
    )
    data = require_list_data(body)
    exam_payloads = extract_exam_payloads(data, site_custom_identifier=site_custom_identifier, pull_source="getExamsByDate")
    summary = _dry_run_summary(exam_payloads) if dry_run else upsert_exam_payloads(db, connection_id=connection_id, payloads=exam_payloads)
    return {
        "connection_id": connection_id,
        "dry_run": dry_run,
        "start_date": start_date,
        "end_date": end_date,
        "site_custom_identifier": site_custom_identifier,
        "summary": summary.as_dict(),
    }


def pull_latest_patient_exam(db: Session, connection_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    connection = _get_connection(db, connection_id)
    site_identifier = _required_string(payload, "site_identifier")
    mrn = _required_string(payload, "mrn")
    dry_run = bool(payload.get("dry_run", False))

    body = RemidioClient(_secrets(connection)).get_patient_with_last_exam(site_identifier=site_identifier, mrn=mrn)
    data = require_gateway_ok(body)
    exam_items = [data] if isinstance(data, dict) else data
    if not isinstance(exam_items, list):
        raise RemidioConfigError("Remidio latest-patient response did not contain an exam.")
    exam_payloads = extract_exam_payloads(exam_items, site_custom_identifier=None, pull_source="getPatientWithLastExam")
    summary = _dry_run_summary(exam_payloads) if dry_run else upsert_exam_payloads(db, connection_id=connection_id, payloads=exam_payloads)
    return {
        "connection_id": connection_id,
        "dry_run": dry_run,
        "site_identifier": site_identifier,
        "summary": summary.as_dict(),
    }


def ingest_connection_files(db: Session, connection_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    connection = _get_connection(db, connection_id)
    client = RemidioClient(_secrets(connection))
    return ingest_staged_files(db, connection_id=connection.id, client=client, payload=payload)


def create_routing_profile_sync_job(
    db: Session,
    *,
    routing_profile_id: int,
    payload: dict[str, Any],
    requested_by_user_id: int | None = None,
    requested_by_username: str | None = None,
) -> dict[str, Any]:
    routing_profile = _load_routing_profile_for_sync(db, routing_profile_id)
    _require_sync_lab_scope(db, routing_profile, requested_by_user_id)
    if not any(route.active and route.source_rule and route.source_rule.active for route in routing_profile.routes):
        raise RemidioConfigError("No active Remidio API routes are available for this routing profile.")
    start_date = normalize_date(_required_string(payload, "start_date"))
    end_date = normalize_date(_required_string(payload, "end_date"))
    limit = min(max(_optional_int(payload.get("limit")) or 20, 1), 200)
    route_ids = _optional_int_list(payload.get("route_ids"))
    dry_run = _optional_bool(payload.get("dry_run"), default=False)

    job = Job(
        token=f"remidio-api-sync-{uuid4()}",
        status="queued",
        upload_type="remidio api routing sync",
        upload_kind="encounter_set",
        project_id=routing_profile.project_id,
        uploader_user_id=requested_by_user_id,
        uploader_username=requested_by_username,
    )
    db.add(job)
    db.flush()
    item_payload = {
        "routing_profile_id": routing_profile.id,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "route_ids": route_ids,
        "dry_run": dry_run,
    }
    item = JobItem(
        job_id=job.id,
        filename=f"Remidio API sync: {routing_profile.name}",
        state="queued",
        detail=json.dumps(item_payload),
        uploader_user_id=requested_by_user_id,
        uploader_username=requested_by_username,
        source_type=REMIDIO_API_SYNC_ITEM_SOURCE,
        source_id=routing_profile.id,
    )
    db.add(item)
    db.flush()
    return {"job_id": job.id, "job_token": job.token, "job_item_id": item.id, "routing_profile_id": routing_profile.id}


def enqueue_routing_profile_sync_job(job_id: int, *, user_id: int | None = None, hospital_id: int | None = None) -> None:
    from utils.celery_helpers import celery_enabled, enqueue_task

    if celery_enabled():
        enqueue_task(REMIDIO_API_SYNC_TASK_NAME, job_id, user_id=user_id, hospital_id=hospital_id)
        return
    run_routing_profile_sync_job(job_id)


def run_routing_profile_sync_job(job_id: int) -> dict[str, Any]:
    with get_db_session() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        item = (
            db.query(JobItem)
            .filter(JobItem.job_id == job.id, JobItem.source_type == REMIDIO_API_SYNC_ITEM_SOURCE)
            .order_by(JobItem.id.asc())
            .first()
        )
        if item is None:
            job.status = "failed"
            job.error = "Remidio API sync job item not found."
            job.updated_at = utcnow()
            db.add(job)
            db.commit()
            return {"job_id": job_id, "status": "failed", "error": job.error}
        try:
            payload = json.loads(item.detail or "{}")
        except json.JSONDecodeError as exc:
            job.status = "failed"
            item.state = "failed"
            item.detail = f"Invalid Remidio API sync payload: {sanitize_log_value(exc)}"
            item.finished_at = utcnow()
            job.error = item.detail
            job.updated_at = utcnow()
            db.add_all([job, item])
            db.commit()
            return {"job_id": job_id, "status": "failed", "error": job.error}

        job.status = "processing"
        item.state = "processing"
        item.started_at = utcnow()
        job.updated_at = utcnow()
        db.add_all([job, item])
        db.commit()

    try:
        result = _run_routing_profile_sync_payload(payload)
        with get_db_session() as db:
            job = db.get(Job, job_id)
            item = (
                db.query(JobItem)
                .filter(JobItem.job_id == job_id, JobItem.source_type == REMIDIO_API_SYNC_ITEM_SOURCE)
                .order_by(JobItem.id.asc())
                .first()
            )
            if job:
                job.status = "completed"
                job.error = None
                job.updated_at = utcnow()
                db.add(job)
            if item:
                item.state = "completed"
                item.detail = json.dumps(result)
                item.finished_at = utcnow()
                db.add(item)
            db.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        error = str(sanitize_log_value(exc))[:1000]
        with get_db_session() as db:
            job = db.get(Job, job_id)
            item = (
                db.query(JobItem)
                .filter(JobItem.job_id == job_id, JobItem.source_type == REMIDIO_API_SYNC_ITEM_SOURCE)
                .order_by(JobItem.id.asc())
                .first()
            )
            if job:
                job.status = "failed"
                job.error = error
                job.updated_at = utcnow()
                db.add(job)
            if item:
                item.state = "failed"
                item.detail = error
                item.finished_at = utcnow()
                db.add(item)
            db.commit()
        raise


def _run_routing_profile_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    routing_profile_id = _required_int(payload, "routing_profile_id")
    start_date = _required_string(payload, "start_date")
    end_date = _required_string(payload, "end_date")
    limit = min(max(_optional_int(payload.get("limit")) or 20, 1), 200)
    route_ids = set(_optional_int_list(payload.get("route_ids")) or [])
    dry_run = _optional_bool(payload.get("dry_run"), default=False)

    summaries: list[dict[str, Any]] = []
    with get_db_session() as db:
        routing_profile = _load_routing_profile_for_sync(db, routing_profile_id)
        routes = [route for route in routing_profile.routes if route.active and route.source_rule and route.source_rule.active]
        if route_ids:
            routes = [route for route in routes if route.id in route_ids]
        if not routes:
            raise RemidioConfigError("No active Remidio API routes are available for this routing profile.")

        grouped: dict[tuple[int, str], list[ProjectUploadProfileRemidioApiBinding]] = {}
        for route in routes:
            key = (route.source_rule.remidio_connection_id, route.source_rule.site_custom_identifier)
            grouped.setdefault(key, []).append(route)

        for (connection_id, site_custom_identifier), group_routes in grouped.items():
            pull_result = pull_exams_by_date(
                db,
                connection_id,
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "site_custom_identifier": site_custom_identifier,
                    "dry_run": dry_run,
                },
            )
            ingest_result = None
            if not dry_run:
                ingest_result = ingest_connection_files(
                    db,
                    connection_id,
                    {
                        "site_custom_identifier": site_custom_identifier,
                        "start_date": start_date,
                        "end_date": end_date,
                        "limit": limit,
                        "pending_only": True,
                        "include_images": True,
                        "include_reports": True,
                        "remidio_api_binding_ids": [route.id for route in group_routes],
                    },
                )
            summaries.append(
                {
                    "connection_id": connection_id,
                    "site_custom_identifier": site_custom_identifier,
                    "route_ids": [route.id for route in group_routes],
                    "pull": pull_result,
                    "ingest": ingest_result,
                }
            )
        db.commit()

    return {
        "routing_profile_id": routing_profile_id,
        "dry_run": dry_run,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "groups": summaries,
    }


def _secrets(connection: RemidioConnection) -> RemidioSecrets:
    return RemidioSecrets(
        base_url=connection.base_url,
        client_name=connection.client_name,
        client_identification_token=decrypt_password_with_salt(connection.client_identification_token_encrypted, connection.secret_salt),
        email=decrypt_password_with_salt(connection.email_encrypted, connection.secret_salt),
        password=decrypt_password_with_salt(connection.password_encrypted, connection.secret_salt),
    )


def _load_routing_profile_for_sync(db: Session, routing_profile_id: int) -> RemidioApiRoutingProfile:
    routing_profile = (
        db.query(RemidioApiRoutingProfile)
        .options(
            selectinload(RemidioApiRoutingProfile.project),
            selectinload(RemidioApiRoutingProfile.routes)
            .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule),
            selectinload(RemidioApiRoutingProfile.routes)
            .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile),
            selectinload(RemidioApiRoutingProfile.routes).selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
        )
        .filter(RemidioApiRoutingProfile.id == routing_profile_id)
        .one_or_none()
    )
    if routing_profile is None or not routing_profile.active:
        raise RemidioConfigError("Remidio API routing profile was not found or inactive.")
    return routing_profile


def _require_sync_lab_scope(db: Session, routing_profile: RemidioApiRoutingProfile, user_id: int | None) -> None:
    if user_id is None:
        return
    scoped_lab_ids = manager_lab_unit_ids(user_id)
    route_lab_ids = {route.lab_unit_id for route in routing_profile.routes if route.active}
    if route_lab_ids and not route_lab_ids.issubset(scoped_lab_ids):
        raise RemidioConfigError("You cannot sync Remidio API routes outside your lab-unit scope.")


def _dry_run_summary(payloads: list[RemidioExamPayload]) -> UpsertSummary:
    return UpsertSummary(
        exams_seen=len(payloads),
        images_seen=sum(len(payload.images) for payload in payloads),
        reports_seen=sum(len(payload.reports) for payload in payloads),
    )


def _connection_summary(connection: RemidioConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "name": connection.name,
        "project_id": connection.project_id,
        "base_url": connection.base_url,
        "client_name": connection.client_name,
        "active": connection.active,
        "site_count": len(connection.sites or []),
        "last_login_at": _iso(connection.last_login_at),
        "last_auth_token_at": _iso(connection.last_auth_token_at),
        "created_at": _iso(connection.created_at),
        "updated_at": _iso(connection.updated_at),
    }


def _site_summary(site: RemidioSite) -> dict[str, Any]:
    return {
        "id": site.id,
        "remidio_connection_id": site.remidio_connection_id,
        "remidio_site_id": site.remidio_site_id,
        "site_name": site.site_name,
        "site_domain": site.site_domain,
        "site_custom_identifier": site.site_custom_identifier,
        "active": site.active,
        "created_at": _iso(site.created_at),
        "updated_at": _iso(site.updated_at),
    }


def _routing_rule_summary(rule: RemidioRoutingRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "remidio_connection_id": rule.remidio_connection_id,
        "remidio_site_id": rule.remidio_site_id,
        "site_custom_identifier": rule.site_custom_identifier,
        "remidio_device_type": rule.remidio_device_type,
        "project_id": rule.project_id,
        "project_title": rule.project.title if rule.project else None,
        "lab_unit_id": rule.lab_unit_id,
        "lab_unit_name": rule.lab_unit.name if rule.lab_unit else None,
        "camera_id": rule.camera_id,
        "camera_name": rule.camera.name if rule.camera else None,
        "default_disease_id": rule.default_disease_id,
        "default_disease_name": rule.default_disease.name if rule.default_disease else None,
        "active": rule.active,
        "created_at": _iso(rule.created_at),
        "updated_at": _iso(rule.updated_at),
    }


def _get_connection(db: Session, connection_id: int) -> RemidioConnection:
    connection = db.get(RemidioConnection, connection_id)
    if connection is None:
        raise RemidioConfigError("Remidio connection was not found.")
    if not connection.active:
        raise RemidioConfigError("Remidio connection is inactive.")
    return connection


def _require_row(db: Session, model: type, row_id: int, field_name: str) -> None:
    if db.get(model, row_id) is None:
        raise RemidioConfigError(f"{field_name} does not exist.")


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        raise RemidioConfigError(f"{field_name} is required.")
    return str(value).strip()


def _required_int(payload: dict[str, Any], field_name: str) -> int:
    value = _optional_int(payload.get(field_name))
    if value is None:
        raise RemidioConfigError(f"{field_name} is required.")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RemidioConfigError("Expected an integer identifier.")


def _optional_int_list(value: Any) -> list[int] | None:
    if value is None or value == "":
        return None
    if not isinstance(value, list):
        raise RemidioConfigError("Expected a list of integer identifiers.")
    try:
        return [int(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise RemidioConfigError("Expected a list of integer identifiers.") from exc


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _normalize_base_url(value: str) -> str:
    normalized = str(value).strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise RemidioConfigError("base_url must start with http:// or https://.")
    return normalized


def _iso(value) -> str | None:
    return value.isoformat() if value else None
