"""Use cases for configuring and pulling Remidio API data."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import (
    Camera,
    Disease,
    EncounterSetImage,
    EncounterSetAttachment,
    Job,
    JobItem,
    LabUnit,
    PatientEncounters,
    Project,
    RemidioExam,
    RemidioImage,
    RemidioReport,
    RemidioConnection,
    RemidioRoutingRule,
    RemidioSite,
)
from upload_profiles.models import ProjectUploadProfile
from upload_profiles.service import manager_lab_unit_ids
from utils.encryption import decrypt_password_with_salt, encrypt_password_with_salt, generate_salt
from utils.hospital_scoping import apply_scoping
from utils.log_sanitize import sanitize_log_value

from .client import RemidioClient
from .errors import RemidioConfigError, RemidioRemoteError
from .ingest import ingest_staged_files
from .models import (
    ProjectUploadProfileRemidioApiBinding,
    RemidioApiExamEncounter,
    RemidioApiRoutingProfile,
    RemidioApiSourceRule,
)
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
REMIDIO_API_PROJECT_SYNC_TASK_NAME = "celery_tasks.tasks.remidio_tasks.run_remidio_api_project_sync_task"
REMIDIO_API_PROJECT_PROSPECTIVE_TASK_NAME = "celery_tasks.tasks.remidio_tasks.queue_remidio_api_prospective_project_syncs_task"
REMIDIO_API_PROJECT_SYNC_ITEM_SOURCE = "remidio_api_project_sync"
REMIDIO_API_PROJECT_SYNC_UPLOAD_TYPE = "remidio api project sync"
LOGGER = logging.getLogger("remidio_api_integration.service")


def list_encounter_set_browser(
    db: Session,
    *,
    user,
    project_id: int | None = None,
    selected_date: date | None = None,
    selected_month: str | None = None,
    encounter_id: int | None = None,
) -> dict[str, Any]:
    projects = _encounter_set_browser_projects(db, user)
    selected_project_id = project_id if any(project["id"] == project_id for project in projects) else None
    if selected_project_id is None and projects:
        selected_project_id = projects[0]["id"]

    dates: list[dict[str, Any]] = []
    patients: list[dict[str, Any]] = []
    selected_encounter_id: int | None = None
    detail: dict[str, Any] | None = None

    if selected_project_id:
        all_dates = _encounter_set_browser_dates(db, user, selected_project_id)
        months = _encounter_set_browser_months(all_dates)
        if selected_date:
            selected_month = selected_date.strftime("%Y-%m")
        elif selected_month not in {month["value"] for month in months}:
            selected_month = months[0]["value"] if months else None
        dates = [row for row in all_dates if not selected_month or row["date"].strftime("%Y-%m") == selected_month]
        available_dates = {row["date"] for row in dates}
        if selected_date not in available_dates:
            selected_date = dates[0]["date"] if dates else None
        if selected_date:
            patients = _encounter_set_browser_patients(db, user, selected_project_id, selected_date)
            if encounter_id and any(row["id"] == encounter_id for row in patients):
                selected_encounter_id = encounter_id
            elif patients:
                selected_encounter_id = patients[0]["id"]
            if selected_encounter_id:
                detail = _encounter_set_browser_detail(db, user, selected_encounter_id)

    return {
        "projects": projects,
        "selected_project_id": selected_project_id,
        "months": months if selected_project_id else [],
        "selected_month": selected_month,
        "dates": dates,
        "selected_date": selected_date,
        "patients": patients,
        "selected_encounter_id": selected_encounter_id,
        "detail": detail,
    }


def _encounter_set_browser_projects(db: Session, user) -> list[dict[str, Any]]:
    query = (
        db.query(Project, func.count(PatientEncounters.id).label("encounter_count"))
        .join(PatientEncounters, PatientEncounters.project_id == Project.id)
        .filter(PatientEncounters.is_set_based.is_(True), Project.active.is_(True))
        .group_by(Project.id)
        .order_by(Project.title.asc())
    )
    query = apply_scoping(query, PatientEncounters, user, "upload")
    return [
        {
            "id": project.id,
            "title": project.title,
            "code": project.code,
            "encounter_count": encounter_count,
        }
        for project, encounter_count in query.all()
    ]


def _encounter_set_browser_dates(db: Session, user, project_id: int) -> list[dict[str, Any]]:
    query = (
        db.query(PatientEncounters.capture_date_dt, func.count(PatientEncounters.id))
        .filter(
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.project_id == project_id,
            PatientEncounters.capture_date_dt.isnot(None),
        )
        .group_by(PatientEncounters.capture_date_dt)
        .order_by(PatientEncounters.capture_date_dt.desc())
    )
    query = apply_scoping(query, PatientEncounters, user, "upload")
    return [
        {
            "date": capture_date,
            "label": capture_date.strftime("%d %b"),
            "count": count,
        }
        for capture_date, count in query.all()
    ]


def _encounter_set_browser_months(dates: list[dict[str, Any]]) -> list[dict[str, str]]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    order: list[str] = []
    for row in dates:
        value = row["date"].strftime("%Y-%m")
        if value not in counts:
            order.append(value)
            labels[value] = row["date"].strftime("%b %Y")
            counts[value] = 0
        counts[value] += int(row.get("count") or 0)
    months: list[dict[str, str]] = []
    for value in order:
        months.append({"value": value, "label": f"{labels[value]} ({counts[value]})"})
    return months


def _encounter_set_browser_patients(db: Session, user, project_id: int, selected_date: date) -> list[dict[str, Any]]:
    query = (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.encounter_set_images),
            selectinload(PatientEncounters.encounter_set_attachments),
            selectinload(PatientEncounters.lab_unit),
            selectinload(PatientEncounters.upload_profile),
        )
        .filter(
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.project_id == project_id,
            PatientEncounters.capture_date_dt == selected_date,
        )
        .order_by(PatientEncounters.name.asc(), PatientEncounters.patient_id.asc(), PatientEncounters.id.asc())
        .limit(300)
    )
    query = apply_scoping(query, PatientEncounters, user, "upload")
    return [_encounter_set_patient_row(encounter) for encounter in query.all()]


def _encounter_set_browser_detail(db: Session, user, encounter_id: int) -> dict[str, Any] | None:
    query = (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.project),
            selectinload(PatientEncounters.upload_profile),
            selectinload(PatientEncounters.lab_unit),
            selectinload(PatientEncounters.encounter_set_images).selectinload(EncounterSetImage.camera),
            selectinload(PatientEncounters.encounter_set_attachments),
        )
        .filter(PatientEncounters.id == encounter_id, PatientEncounters.is_set_based.is_(True))
    )
    query = apply_scoping(query, PatientEncounters, user, "upload")
    encounter = query.first()
    if encounter is None:
        return None
    metadata = encounter.metadata_json or {}
    encounter_metadata = metadata.get("encounter") if isinstance(metadata.get("encounter"), dict) else {}
    remidio_exam = (
        db.query(RemidioExam)
        .filter(RemidioExam.patient_encounter_id == encounter.id)
        .options(selectinload(RemidioExam.images), selectinload(RemidioExam.reports))
        .first()
    )
    images = [_encounter_set_image_row(image) for image in sorted(encounter.encounter_set_images, key=lambda img: img.spatial_position)]
    return {
        **_encounter_set_patient_row(encounter),
        "uuid": encounter.uuid,
        "capture_date": encounter.capture_date,
        "capture_date_dt": encounter.capture_date_dt,
        "capture_datetime": _parse_iso_datetime(_metadata_lookup(encounter_metadata, "capture_datetime"))
        or (remidio_exam.exam_date if remidio_exam else None),
        "project_title": encounter.project.title if encounter.project else None,
        "project_code": encounter.project.code if encounter.project else None,
        "upload_profile_name": encounter.upload_profile.name if encounter.upload_profile else None,
        "lab_unit_name": encounter.lab_unit.name if encounter.lab_unit else None,
        "verified_status": encounter.encounter_verified_status or "pending",
        "metadata_patient": metadata.get("patient") if isinstance(metadata.get("patient"), dict) else {},
        "metadata_encounter": encounter_metadata,
        "metadata_other": {
            key: value
            for key, value in metadata.items()
            if key not in {"patient", "encounter"} and _has_value(value)
        }
        if isinstance(metadata, dict)
        else {},
        "remidio_exam_id": remidio_exam.remidio_exam_id if remidio_exam else _metadata_lookup(metadata, "remidio_exam_id"),
        "remidio_site": remidio_exam.site_custom_identifier if remidio_exam else _metadata_lookup(metadata, "remidio_site_custom_identifier"),
        "images": images,
        "image_groups": _group_encounter_set_images(images),
        "attachments": [
            _encounter_set_attachment_row(attachment)
            for attachment in sorted(
                encounter.encounter_set_attachments,
                key=lambda item: item.created_at.isoformat() if item.created_at else "",
            )
        ],
    }


def _encounter_set_patient_row(encounter: PatientEncounters) -> dict[str, Any]:
    metadata = encounter.metadata_json or {}
    patient_metadata = metadata.get("patient") if isinstance(metadata.get("patient"), dict) else {}
    patient_name = _metadata_lookup(patient_metadata, "patient_name")
    return {
        "id": encounter.id,
        "uuid": encounter.uuid,
        "name": patient_name or encounter.name,
        "mrn": encounter.patient_id,
        "age": _metadata_lookup(patient_metadata, "patient_age_yrs", "age", "age_yrs"),
        "sex": _metadata_lookup(patient_metadata, "sex", "gender"),
        "capture_date_dt": encounter.capture_date_dt,
        "capture_date": encounter.capture_date,
        "verified_status": encounter.encounter_verified_status or "pending",
        "image_count": len(encounter.encounter_set_images or []),
        "attachment_count": len(encounter.encounter_set_attachments or []),
        "lab_unit_name": encounter.lab_unit.name if encounter.lab_unit else None,
        "upload_profile_name": encounter.upload_profile.name if encounter.upload_profile else None,
    }


def _encounter_set_image_row(image: EncounterSetImage) -> dict[str, Any]:
    metadata = image.metadata_json or {}
    return {
        "id": image.id,
        "uuid": image.uuid,
        "position": image.spatial_position,
        "filename": image.original_filename,
        "thumbnail_filename": image.thumbnail_filename,
        "camera_name": image.camera.name if image.camera else None,
        "laterality": _metadata_lookup(metadata, "laterality"),
        "field": _metadata_lookup(metadata, "fundus_field", "field"),
        "quality": _metadata_lookup(metadata, "remidio_image_quality", "quality"),
        "device_type": _metadata_lookup(metadata, "image_device_type", "device_type"),
        "remidio_image_id": _metadata_lookup(metadata, "remidio_image_id"),
        "creates_task": image.creates_task,
        "visible_to_grader": image.visible_to_grader,
        "is_reviewed": image.is_reviewed,
        "is_not_gradable": image.is_not_gradable,
    }


def _encounter_set_attachment_row(attachment: EncounterSetAttachment) -> dict[str, Any]:
    metadata = attachment.metadata_json or {}
    return {
        "id": attachment.id,
        "uuid": attachment.uuid,
        "asset_kind": attachment.asset_kind,
        "filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "file_size_bytes": attachment.file_size_bytes,
        "report_type": _metadata_lookup(metadata, "remidio_report_type"),
        "remidio_report_id": _metadata_lookup(metadata, "remidio_report_id"),
        "visible_to_grader": attachment.visible_to_grader,
        "is_reviewed": attachment.is_reviewed,
    }


def _group_encounter_set_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = [
        ("OD", "OD"),
        ("OS", "OS"),
        ("Other", "Other"),
    ]
    grouped: list[dict[str, Any]] = []
    for key, label in groups:
        if key == "Other":
            group_images = [image for image in images if image.get("laterality") not in {"OD", "OS"}]
        else:
            group_images = [image for image in images if image.get("laterality") == key]
        if group_images:
            grouped.append({"key": key, "label": label, "images": group_images})
    return grouped


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _metadata_lookup(metadata: dict[str, Any] | None, *keys: str) -> Any:
    if not isinstance(metadata, dict):
        return None
    for key in keys:
        value = metadata.get(key)
        if _has_value(value):
            return value
    return None


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


def ingest_connection_files(
    db: Session,
    connection_id: int,
    payload: dict[str, Any],
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    connection = _get_connection(db, connection_id)
    client = RemidioClient(_secrets(connection))
    return ingest_staged_files(db, connection_id=connection.id, client=client, payload=payload, progress_callback=progress_callback)


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


def create_project_sync_job(
    db: Session,
    *,
    project_id: int,
    payload: dict[str, Any],
    requested_by_user_id: int | None = None,
    requested_by_username: str | None = None,
    skip_active_duplicates: bool = False,
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if project is None or not project.active:
        raise RemidioConfigError("Project was not found or inactive.")
    _require_project_sync_lab_scope(db, project_id, requested_by_user_id)

    start_date = _parse_date(_required_string(payload, "start_date"))
    end_date = _parse_date(_required_string(payload, "end_date"))
    if end_date < start_date:
        raise RemidioConfigError("end_date must be on or after start_date.")
    mode = (payload.get("mode") or "historical_manual").strip() or "historical_manual"
    dry_run = _optional_bool(payload.get("dry_run"), default=False)
    limit = min(max(_optional_int(payload.get("limit")) or 50, 1), 200)

    route_groups = _project_route_groups(db, project_id)
    if not route_groups:
        raise RemidioConfigError("No active Remidio API routes are available for this project.")

    job = Job(
        token=f"remidio-api-project-sync-{uuid4()}",
        status="queued",
        upload_type=REMIDIO_API_PROJECT_SYNC_UPLOAD_TYPE,
        upload_kind="encounter_set",
        project_id=project_id,
        uploader_user_id=requested_by_user_id,
        uploader_username=requested_by_username,
    )
    db.add(job)
    db.flush()

    created_items = 0
    skipped_items = 0
    for slice_start, slice_end in _daily_slices_newest_first(start_date, end_date):
        for group in route_groups:
            item_payload = {
                "project_id": project_id,
                "routing_profile_id": group["routing_profile_id"],
                "route_ids": group["route_ids"],
                "start_date": slice_start.isoformat(),
                "end_date": slice_end.isoformat(),
                "limit": limit,
                "dry_run": dry_run,
                "mode": mode,
            }
            if skip_active_duplicates and _active_project_sync_item_exists(db, item_payload):
                skipped_items += 1
                continue
            db.add(
                JobItem(
                    job_id=job.id,
                    filename=f"Remidio API sync: {project.title} {slice_start.isoformat()} {group['routing_profile_name']}",
                    state="queued",
                    detail=json.dumps(item_payload),
                    uploader_user_id=requested_by_user_id,
                    uploader_username=requested_by_username,
                    source_type=REMIDIO_API_PROJECT_SYNC_ITEM_SOURCE,
                    source_id=project_id,
                )
            )
            created_items += 1

    if created_items == 0:
        job.status = "completed"
        job.error = "No new sync items were queued; matching active items already exist."
    db.flush()
    return {
        "job_id": job.id,
        "job_token": job.token,
        "project_id": project_id,
        "items_created": created_items,
        "items_skipped": skipped_items,
        "mode": mode,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def create_prospective_project_sync_jobs() -> dict[str, Any]:
    today = utcnow().date()
    payload = {
        "start_date": (today - timedelta(days=1)).isoformat(),
        "end_date": today.isoformat(),
        "mode": "prospective_hourly",
        "limit": 100,
        "dry_run": False,
    }
    queued: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with get_db_session() as db:
        project_ids = _eligible_project_ids_for_auto_sync(db)
        for project_id in project_ids:
            try:
                result = create_project_sync_job(
                    db,
                    project_id=project_id,
                    payload=payload,
                    skip_active_duplicates=True,
                )
                queued.append(result)
            except RemidioConfigError as exc:
                errors.append({"project_id": project_id, "error": str(sanitize_log_value(exc))})
        db.commit()
    for item in queued:
        if item["items_created"] > 0:
            enqueue_project_sync_job(item["job_id"])
    return {"projects_seen": len(queued) + len(errors), "queued": queued, "errors": errors}


def enqueue_project_sync_job(job_id: int, *, user_id: int | None = None, hospital_id: int | None = None) -> None:
    from utils.celery_helpers import celery_enabled, enqueue_task

    if celery_enabled():
        enqueue_task(REMIDIO_API_PROJECT_SYNC_TASK_NAME, job_id, user_id=user_id, hospital_id=hospital_id)
        return
    run_project_sync_job(job_id)


def pause_project_sync_job(db: Session, job_id: int) -> dict[str, Any]:
    job = _project_sync_job_for_action(db, job_id)
    if job.status in {"completed", "failed", "partial_error", "cancelled"}:
        raise RemidioConfigError("Only queued or processing Remidio API sync jobs can be paused.")
    job.status = "paused"
    job.error = "Paused by user."
    job.updated_at = utcnow()
    db.add(job)
    db.flush()
    return {"job_id": job.id, "status": job.status}


def resume_project_sync_job(db: Session, job_id: int) -> dict[str, Any]:
    job = _project_sync_job_for_action(db, job_id)
    if job.status in {"completed", "cancelled"}:
        raise RemidioConfigError("Completed or cancelled Remidio API sync jobs cannot be resumed.")
    stale_processing = (
        db.query(JobItem)
        .filter(
            JobItem.job_id == job.id,
            JobItem.source_type == REMIDIO_API_PROJECT_SYNC_ITEM_SOURCE,
            JobItem.state == "processing",
        )
        .all()
    )
    for item in stale_processing:
        item.state = "queued"
        item.finished_at = None
        db.add(item)
    job.status = "queued"
    job.error = None
    job.updated_at = utcnow()
    db.add(job)
    db.flush()
    return {"job_id": job.id, "status": job.status, "reset_processing_items": len(stale_processing)}


def cancel_project_sync_job(db: Session, job_id: int) -> dict[str, Any]:
    job = _project_sync_job_for_action(db, job_id)
    if job.status in {"completed", "cancelled"}:
        raise RemidioConfigError("This Remidio API sync job is already finished.")
    pending_items = (
        db.query(JobItem)
        .filter(
            JobItem.job_id == job.id,
            JobItem.source_type == REMIDIO_API_PROJECT_SYNC_ITEM_SOURCE,
            JobItem.state.in_(["queued", "processing"]),
        )
        .all()
    )
    for item in pending_items:
        item.state = "cancelled"
        item.finished_at = utcnow()
        db.add(item)
    job.status = "cancelled"
    job.error = "Cancelled by user."
    job.updated_at = utcnow()
    db.add(job)
    db.flush()
    return {"job_id": job.id, "status": job.status, "cancelled_items": len(pending_items)}


def run_project_sync_job(job_id: int) -> dict[str, Any]:
    with get_db_session() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"job_id": job_id, "status": "missing"}
        items = (
            db.query(JobItem)
            .filter(JobItem.job_id == job.id, JobItem.source_type == REMIDIO_API_PROJECT_SYNC_ITEM_SOURCE)
            .filter(JobItem.state != "completed")
            .order_by(JobItem.id.asc())
            .all()
        )
        if not items:
            job.status = "completed"
            job.error = None
            job.updated_at = utcnow()
            db.add(job)
            db.commit()
            return {"job_id": job_id, "status": "completed", "items": []}
        item_ids = [item.id for item in items]
        job.status = "processing"
        job.updated_at = utcnow()
        db.add(job)
        db.commit()

    results: list[dict[str, Any]] = []
    failed = 0
    for item_id in item_ids:
        with get_db_session() as db:
            job = db.get(Job, job_id)
            if job and job.status in {"paused", "cancelled"}:
                return {"job_id": job_id, "status": job.status, "items": results}
        result = _run_project_sync_item(job_id, item_id)
        results.append(result)
        if result.get("status") == "failed":
            failed += 1

    with get_db_session() as db:
        job = db.get(Job, job_id)
        if job:
            if job.status in {"paused", "cancelled"}:
                db.commit()
                return {"job_id": job_id, "status": job.status, "items": results}
            if failed == 0:
                job.status = "completed"
                job.error = None
            elif failed == len(results):
                job.status = "failed"
                job.error = f"{failed} Remidio API sync item(s) failed."
            else:
                job.status = "partial_error"
                job.error = f"{failed} Remidio API sync item(s) failed."
            job.updated_at = utcnow()
            db.add(job)
            db.commit()
    return {"job_id": job_id, "status": "completed" if failed == 0 else "partial_error", "items": results}


def list_project_sync_dashboard(db: Session, *, project_id: int | None = None) -> dict[str, Any]:
    projects = _projects_with_routing(db)
    selected_project_id = project_id or (projects[0]["id"] if projects else None)
    routes = []
    windows = []
    jobs = []
    failures = []
    if selected_project_id:
        routes = _project_route_summaries(db, selected_project_id)
        today = utcnow().date()
        windows = [
            _sync_window_summary(db, selected_project_id, today, "Today"),
            _sync_window_summary(db, selected_project_id, today - timedelta(days=1), "Yesterday"),
        ]
        jobs = _recent_project_sync_jobs(db, selected_project_id)
        failures = _failed_or_pending_assets(db, selected_project_id)
    return {
        "projects": projects,
        "selected_project_id": selected_project_id,
        "routes": routes,
        "windows": windows,
        "jobs": jobs,
        "has_active_jobs": any(
            job["status"] in {"queued", "processing"}
            or (
                job["status"] not in {"paused", "cancelled", "completed", "failed", "partial_error"}
                and (job["queued_count"] > 0 or job["processing_count"] > 0)
            )
            for job in jobs
        ),
        "failures": failures,
    }


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
        diagnostics = _remidio_exception_diagnostics(exc)
        LOGGER.warning(
            "Remidio API routing profile sync failed job_id=%s error=%s diagnostics=%s",
            sanitize_log_value(job_id),
            sanitize_log_value(error, max_len=1000),
            sanitize_log_value(diagnostics, max_len=1500),
        )
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
                item.detail = json.dumps({"error": error, "diagnostics": diagnostics})
                item.finished_at = utcnow()
                db.add(item)
            db.commit()
        raise


def _run_routing_profile_sync_payload(
    payload: dict[str, Any],
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
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
            LOGGER.info(
                "Remidio API route pull start routing_profile_id=%s connection_id=%s site=%s start_date=%s end_date=%s route_ids=%s",
                sanitize_log_value(routing_profile_id),
                sanitize_log_value(connection_id),
                sanitize_log_value(site_custom_identifier),
                sanitize_log_value(start_date),
                sanitize_log_value(end_date),
                sanitize_log_value([route.id for route in group_routes], max_len=500),
            )
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
                    progress_callback=progress_callback,
                )
            LOGGER.info(
                "Remidio API route pull complete routing_profile_id=%s connection_id=%s site=%s start_date=%s end_date=%s pull_summary=%s ingest_summary=%s",
                sanitize_log_value(routing_profile_id),
                sanitize_log_value(connection_id),
                sanitize_log_value(site_custom_identifier),
                sanitize_log_value(start_date),
                sanitize_log_value(end_date),
                sanitize_log_value((pull_result.get("summary") if isinstance(pull_result, dict) else None), max_len=500),
                sanitize_log_value((ingest_result.get("summary") if isinstance(ingest_result, dict) else None), max_len=500),
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


def _run_project_sync_item(job_id: int, item_id: int) -> dict[str, Any]:
    with get_db_session() as db:
        item = db.get(JobItem, item_id)
        if item is None or item.job_id != job_id:
            return {"job_id": job_id, "item_id": item_id, "status": "missing"}
        if item.state == "completed":
            return {"job_id": job_id, "item_id": item_id, "status": "completed", "skipped": True}
        job = db.get(Job, job_id)
        if job and job.status in {"paused", "cancelled"}:
            return {"job_id": job_id, "item_id": item_id, "status": job.status}
        try:
            payload_data = json.loads(item.detail or "{}")
        except json.JSONDecodeError as exc:
            item.state = "failed"
            item.detail = f"Invalid Remidio API sync payload: {sanitize_log_value(exc)}"
            item.finished_at = utcnow()
            db.add(item)
            db.commit()
            return {"job_id": job_id, "item_id": item_id, "status": "failed", "error": item.detail}
        payload = payload_data.get("request") if isinstance(payload_data, dict) and isinstance(payload_data.get("request"), dict) else payload_data
        if not isinstance(payload, dict):
            item.state = "failed"
            item.detail = "Invalid Remidio API sync payload."
            item.finished_at = utcnow()
            db.add(item)
            db.commit()
            return {"job_id": job_id, "item_id": item_id, "status": "failed", "error": item.detail}
        item.state = "processing"
        item.started_at = utcnow()
        db.add(item)
        db.commit()

    try:
        LOGGER.info(
            "Remidio API project sync item start job_id=%s item_id=%s project_id=%s routing_profile_id=%s start_date=%s end_date=%s",
            sanitize_log_value(job_id),
            sanitize_log_value(item_id),
            sanitize_log_value(payload.get("project_id")),
            sanitize_log_value(payload.get("routing_profile_id")),
            sanitize_log_value(payload.get("start_date")),
            sanitize_log_value(payload.get("end_date")),
        )
        progress = _ProjectSyncProgress(job_id=job_id, item_id=item_id, payload=payload)
        _update_project_sync_item_progress(job_id, item_id, payload, progress.snapshot("started"))
        result = _run_routing_profile_sync_payload(payload, progress_callback=progress.update)
        with get_db_session() as db:
            item = db.get(JobItem, item_id)
            if item:
                item.state = "completed"
                item.detail = json.dumps({"request": payload, "result": result})
                item.finished_at = utcnow()
                db.add(item)
                db.commit()
        LOGGER.info(
            "Remidio API project sync item complete job_id=%s item_id=%s project_id=%s start_date=%s end_date=%s",
            sanitize_log_value(job_id),
            sanitize_log_value(item_id),
            sanitize_log_value(payload.get("project_id")),
            sanitize_log_value(payload.get("start_date")),
            sanitize_log_value(payload.get("end_date")),
        )
        return {"job_id": job_id, "item_id": item_id, "status": "completed", "result": result}
    except Exception as exc:  # noqa: BLE001
        error = str(sanitize_log_value(exc))[:1000]
        diagnostics = _remidio_exception_diagnostics(exc)
        LOGGER.warning(
            "Remidio API project sync item failed job_id=%s item_id=%s project_id=%s start_date=%s end_date=%s error=%s diagnostics=%s",
            sanitize_log_value(job_id),
            sanitize_log_value(item_id),
            sanitize_log_value(payload.get("project_id")),
            sanitize_log_value(payload.get("start_date")),
            sanitize_log_value(payload.get("end_date")),
            sanitize_log_value(error, max_len=1000),
            sanitize_log_value(diagnostics, max_len=1500),
        )
        with get_db_session() as db:
            item = db.get(JobItem, item_id)
            if item:
                item.state = "failed"
                item.detail = json.dumps({"request": payload, "error": error, "diagnostics": diagnostics})
                item.finished_at = utcnow()
                db.add(item)
                db.commit()
        return {"job_id": job_id, "item_id": item_id, "status": "failed", "error": error}


def _project_route_groups(db: Session, project_id: int) -> list[dict[str, Any]]:
    profiles = (
        db.query(RemidioApiRoutingProfile)
        .options(
            selectinload(RemidioApiRoutingProfile.routes)
            .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule),
        )
        .filter(
            RemidioApiRoutingProfile.project_id == project_id,
            RemidioApiRoutingProfile.active.is_(True),
        )
        .order_by(RemidioApiRoutingProfile.name.asc())
        .all()
    )
    groups: list[dict[str, Any]] = []
    for profile in profiles:
        route_ids = [
            route.id
            for route in profile.routes
            if route.active and route.source_rule and route.source_rule.active
        ]
        if route_ids:
            groups.append(
                {
                    "routing_profile_id": profile.id,
                    "routing_profile_name": profile.name,
                    "route_ids": sorted(route_ids),
                }
            )
    return groups


def _remidio_exception_diagnostics(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, RemidioRemoteError):
        diagnostics: dict[str, Any] = {}
        if exc.remote_status_code is not None:
            diagnostics["remote_status_code"] = exc.remote_status_code
        if exc.response_snapshot:
            diagnostics["response_snapshot"] = exc.response_snapshot
        return diagnostics
    return {}


class _ProjectSyncProgress:
    def __init__(self, *, job_id: int, item_id: int, payload: dict[str, Any]) -> None:
        self.job_id = job_id
        self.item_id = item_id
        self.payload = payload
        self.started_at = utcnow()
        self.assets_finished = 0
        self.assets_started = 0
        self.last_event: dict[str, Any] = {}

    def update(self, event: dict[str, Any]) -> None:
        if event.get("event") == "download_started":
            self.assets_started += 1
        if event.get("event") == "asset_finished":
            self.assets_finished += 1
        self.last_event = event
        _update_project_sync_item_progress(self.job_id, self.item_id, self.payload, self.snapshot(str(event.get("event") or "processing")))

    def snapshot(self, event_name: str) -> dict[str, Any]:
        elapsed_seconds = max(int((utcnow() - self.started_at).total_seconds()), 0)
        summary = self.last_event.get("summary") if isinstance(self.last_event.get("summary"), dict) else {}
        return {
            "event": event_name,
            "started_at": self.started_at.isoformat(),
            "updated_at": utcnow().isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "assets_started": self.assets_started,
            "assets_finished": self.assets_finished,
            "last_asset_type": self.last_event.get("asset_type"),
            "last_source_id": self.last_event.get("source_id"),
            "last_status": self.last_event.get("status"),
            "last_remidio_exam_id": self.last_event.get("remidio_exam_id"),
            "images_seen": int(summary.get("images_seen") or 0),
            "images_downloaded": int(summary.get("images_downloaded") or 0),
            "images_skipped": int(summary.get("images_skipped") or 0),
            "reports_seen": int(summary.get("reports_seen") or 0),
            "reports_downloaded": int(summary.get("reports_downloaded") or 0),
            "reports_skipped": int(summary.get("reports_skipped") or 0),
            "download_errors": int(summary.get("download_errors") or 0),
            "route_errors": int(summary.get("route_errors") or 0),
        }


def _update_project_sync_item_progress(job_id: int, item_id: int, payload: dict[str, Any], progress: dict[str, Any]) -> None:
    with get_db_session() as db:
        item = db.get(JobItem, item_id)
        if item is None or item.job_id != job_id or item.state != "processing":
            return
        item.detail = json.dumps({"request": payload, "progress": progress})
        db.add(item)
        db.commit()


def _daily_slices_newest_first(start_date: date, end_date: date) -> list[tuple[date, date]]:
    current = end_date
    slices: list[tuple[date, date]] = []
    while current >= start_date:
        slices.append((current, current + timedelta(days=1)))
        current -= timedelta(days=1)
    return slices


def _eligible_project_ids_for_auto_sync(db: Session) -> list[int]:
    rows = (
        db.query(RemidioApiRoutingProfile.project_id)
        .join(ProjectUploadProfileRemidioApiBinding, ProjectUploadProfileRemidioApiBinding.routing_profile_id == RemidioApiRoutingProfile.id)
        .filter(
            RemidioApiRoutingProfile.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
        )
        .distinct()
        .order_by(RemidioApiRoutingProfile.project_id.asc())
        .all()
    )
    return [int(row[0]) for row in rows]


def _active_project_sync_item_exists(db: Session, payload: dict[str, Any]) -> bool:
    active_items = (
        db.query(JobItem)
        .join(Job, Job.id == JobItem.job_id)
        .filter(
            JobItem.source_type == REMIDIO_API_PROJECT_SYNC_ITEM_SOURCE,
            JobItem.source_id == payload["project_id"],
            JobItem.state.in_(["queued", "processing"]),
            Job.status.in_(["queued", "processing"]),
        )
        .order_by(JobItem.id.desc())
        .limit(200)
        .all()
    )
    for item in active_items:
        try:
            existing = json.loads(item.detail or "{}")
        except json.JSONDecodeError:
            continue
        if "request" in existing and isinstance(existing["request"], dict):
            existing = existing["request"]
        if (
            existing.get("project_id") == payload["project_id"]
            and existing.get("routing_profile_id") == payload["routing_profile_id"]
            and existing.get("start_date") == payload["start_date"]
            and existing.get("end_date") == payload["end_date"]
            and sorted(existing.get("route_ids") or []) == sorted(payload.get("route_ids") or [])
        ):
            return True
    return False


def _project_sync_job_for_action(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.upload_type != REMIDIO_API_PROJECT_SYNC_UPLOAD_TYPE:
        raise RemidioConfigError("Remidio API project sync job was not found.")
    return job


def _require_project_sync_lab_scope(db: Session, project_id: int, user_id: int | None) -> None:
    if user_id is None:
        return
    scoped_lab_ids = manager_lab_unit_ids(user_id)
    route_lab_ids = {
        row[0]
        for row in db.query(ProjectUploadProfileRemidioApiBinding.lab_unit_id)
        .join(RemidioApiRoutingProfile, RemidioApiRoutingProfile.id == ProjectUploadProfileRemidioApiBinding.routing_profile_id)
        .filter(
            RemidioApiRoutingProfile.project_id == project_id,
            RemidioApiRoutingProfile.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
        )
        .all()
    }
    if route_lab_ids and not route_lab_ids.issubset(scoped_lab_ids):
        raise RemidioConfigError("You cannot sync Remidio API routes outside your lab-unit scope.")


def _projects_with_routing(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(Project)
        .join(RemidioApiRoutingProfile, RemidioApiRoutingProfile.project_id == Project.id)
        .join(ProjectUploadProfileRemidioApiBinding, ProjectUploadProfileRemidioApiBinding.routing_profile_id == RemidioApiRoutingProfile.id)
        .filter(
            Project.active.is_(True),
            RemidioApiRoutingProfile.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
        )
        .distinct()
        .order_by(Project.title.asc())
        .all()
    )
    return [{"id": row.id, "title": row.title, "code": row.code} for row in rows]


def _project_route_summaries(db: Session, project_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(ProjectUploadProfileRemidioApiBinding)
        .options(
            selectinload(ProjectUploadProfileRemidioApiBinding.routing_profile),
            selectinload(ProjectUploadProfileRemidioApiBinding.source_rule).selectinload(RemidioApiSourceRule.connection),
            selectinload(ProjectUploadProfileRemidioApiBinding.project_profile).selectinload(ProjectUploadProfile.profile),
            selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
            selectinload(ProjectUploadProfileRemidioApiBinding.camera),
        )
        .join(RemidioApiRoutingProfile, RemidioApiRoutingProfile.id == ProjectUploadProfileRemidioApiBinding.routing_profile_id)
        .filter(
            RemidioApiRoutingProfile.project_id == project_id,
            RemidioApiRoutingProfile.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
        )
        .order_by(RemidioApiRoutingProfile.name.asc(), ProjectUploadProfileRemidioApiBinding.id.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "routing_profile_name": row.routing_profile.name if row.routing_profile else None,
            "connection_name": row.source_rule.connection.name if row.source_rule and row.source_rule.connection else None,
            "site_custom_identifier": row.source_rule.site_custom_identifier if row.source_rule else None,
            "device_type": row.source_rule.remidio_device_type if row.source_rule else None,
            "upload_profile_name": row.project_profile.profile.name if row.project_profile and row.project_profile.profile else None,
            "lab_unit_name": row.lab_unit.name if row.lab_unit else None,
            "camera_name": row.camera.name if row.camera else None,
            "active_from_date": row.active_from_date.isoformat() if row.active_from_date else None,
            "active_to_date": row.active_to_date.isoformat() if row.active_to_date else None,
        }
        for row in rows
    ]


def _sync_window_summary(db: Session, project_id: int, day: date, label: str) -> dict[str, Any]:
    start_dt = datetime.combine(day, datetime.min.time()).replace(tzinfo=utcnow().tzinfo)
    end_dt = start_dt + timedelta(days=1)
    routed_exam_ids = (
        select(RemidioApiExamEncounter.remidio_exam_id)
            .join(ProjectUploadProfileRemidioApiBinding, ProjectUploadProfileRemidioApiBinding.id == RemidioApiExamEncounter.remidio_api_binding_id)
            .join(RemidioApiRoutingProfile, RemidioApiRoutingProfile.id == ProjectUploadProfileRemidioApiBinding.routing_profile_id)
            .where(RemidioApiRoutingProfile.project_id == project_id)
    )
    exam_ids = select(RemidioExam.id).where(
        RemidioExam.exam_date >= start_dt,
        RemidioExam.exam_date < end_dt,
        RemidioExam.id.in_(routed_exam_ids),
    )
    exams_count = db.query(func.count(RemidioExam.id)).filter(RemidioExam.id.in_(exam_ids)).scalar() or 0
    images_seen = db.query(func.count(RemidioImage.id)).filter(RemidioImage.remidio_exam_id.in_(exam_ids)).scalar() or 0
    images_downloaded = (
        db.query(func.count(RemidioImage.id))
        .filter(RemidioImage.remidio_exam_id.in_(exam_ids), RemidioImage.encounter_set_image_id.isnot(None))
        .scalar()
        or 0
    )
    reports_seen = db.query(func.count(RemidioReport.id)).filter(RemidioReport.remidio_exam_id.in_(exam_ids)).scalar() or 0
    reports_downloaded = (
        db.query(func.count(RemidioReport.id))
        .filter(RemidioReport.remidio_exam_id.in_(exam_ids), RemidioReport.encounter_set_attachment_id.isnot(None))
        .scalar()
        or 0
    )
    failed = (
        db.query(func.count(RemidioImage.id))
        .filter(RemidioImage.remidio_exam_id.in_(exam_ids), RemidioImage.download_error.isnot(None))
        .scalar()
        or 0
    ) + (
        db.query(func.count(RemidioReport.id))
        .filter(RemidioReport.remidio_exam_id.in_(exam_ids), RemidioReport.download_error.isnot(None))
        .scalar()
        or 0
    )
    return {
        "label": label,
        "day": day.isoformat(),
        "slice": f"{day.isoformat()} -> {(day + timedelta(days=1)).isoformat()}",
        "exams": exams_count,
        "images_seen": images_seen,
        "images_downloaded": images_downloaded,
        "reports_seen": reports_seen,
        "reports_downloaded": reports_downloaded,
        "pending": max(images_seen - images_downloaded, 0) + max(reports_seen - reports_downloaded, 0),
        "failed": failed,
    }


def _recent_project_sync_jobs(db: Session, project_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(Job)
        .options(selectinload(Job.items), selectinload(Job.project))
        .filter(Job.upload_type == REMIDIO_API_PROJECT_SYNC_UPLOAD_TYPE, Job.project_id == project_id)
        .order_by(Job.created_at.desc())
        .limit(20)
        .all()
    )
    return [_project_sync_job_summary(row) for row in rows]


def _project_sync_job_summary(job: Job) -> dict[str, Any]:
    items = sorted(job.items or [], key=lambda item: item.id)
    first_payload = _job_item_payload(items[0]) if items else {}
    windows = []
    start_dates: list[str] = []
    end_dates: list[str] = []
    completed_windows: set[str] = set()
    completed_start_dates: list[str] = []
    active_progress: dict[str, Any] | None = None
    aggregate = {
        "exams_seen": 0,
        "images_seen": 0,
        "images_downloaded": 0,
        "images_skipped": 0,
        "images_failed": 0,
        "images_pending": 0,
        "reports_seen": 0,
        "reports_downloaded": 0,
        "reports_skipped": 0,
        "reports_failed": 0,
        "reports_pending": 0,
        "encounters_created": 0,
        "encounters_reused": 0,
        "pending": 0,
        "failed": 0,
    }
    for item in items:
        payload = _job_item_payload(item)
        if payload:
            window_label = f"{payload.get('start_date')} -> {payload.get('end_date')}"
            windows.append(window_label)
            if payload.get("start_date"):
                start_dates.append(str(payload["start_date"]))
            if payload.get("end_date"):
                end_dates.append(str(payload["end_date"]))
            if item.state in {"completed", "failed"}:
                completed_windows.add(window_label)
                if payload.get("start_date"):
                    completed_start_dates.append(str(payload["start_date"]))
        item_summary = _result_summary(_job_item_result(item))
        for key in aggregate:
            aggregate[key] += int(item_summary.get(key) or 0)
        if item.state == "processing" and active_progress is None:
            active_progress = _job_item_progress(item)
    return {
        "id": job.id,
        "token": job.token,
        "project_title": job.project.title if job.project else None,
        "project_code": job.project.code if job.project else None,
        "status": job.status,
        "error": job.error,
        "mode": first_payload.get("mode"),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "requested_by": job.uploader_username,
        "item_count": len(items),
        "completed_count": sum(1 for item in items if item.state == "completed"),
        "failed_count": sum(1 for item in items if item.state == "failed"),
        "queued_count": sum(1 for item in items if item.state == "queued"),
        "processing_count": sum(1 for item in items if item.state == "processing"),
        "cancelled_count": sum(1 for item in items if item.state == "cancelled"),
        "windows": sorted(set(windows), reverse=True),
        "date_range": f"{min(start_dates)} -> {max(end_dates)}" if start_dates and end_dates else "-",
        "window_count": len(set(windows)),
        "completed_window_count": len(completed_windows),
        "last_processed_date": min(completed_start_dates) if completed_start_dates else None,
        "active_progress": active_progress,
        "summary": aggregate,
        "can_pause": job.status in {"queued", "processing"},
        "can_resume": job.status in {"paused", "processing", "partial_error", "failed"},
        "can_cancel": job.status in {"queued", "processing", "paused", "partial_error", "failed"},
        "items": [_project_sync_item_summary(item) for item in items],
    }


def _project_sync_item_summary(item: JobItem) -> dict[str, Any]:
    payload = _job_item_payload(item)
    result = _job_item_result(item)
    summary = _result_summary(result)
    return {
        "id": item.id,
        "state": item.state,
        "started_at": _iso(item.started_at),
        "finished_at": _iso(item.finished_at),
        "routing_profile_id": payload.get("routing_profile_id"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "route_ids": payload.get("route_ids") or [],
        "summary": summary,
        "progress": _job_item_progress(item),
        "error": _job_item_error(item),
    }


def _failed_or_pending_assets(db: Session, project_id: int) -> list[dict[str, Any]]:
    exam_ids = (
        select(RemidioApiExamEncounter.remidio_exam_id)
        .join(ProjectUploadProfileRemidioApiBinding, ProjectUploadProfileRemidioApiBinding.id == RemidioApiExamEncounter.remidio_api_binding_id)
        .join(RemidioApiRoutingProfile, RemidioApiRoutingProfile.id == ProjectUploadProfileRemidioApiBinding.routing_profile_id)
        .where(RemidioApiRoutingProfile.project_id == project_id)
    )
    image_rows = (
        db.query(RemidioImage, RemidioExam)
        .join(RemidioExam, RemidioExam.id == RemidioImage.remidio_exam_id)
        .filter(
            RemidioImage.remidio_exam_id.in_(exam_ids),
            or_(RemidioImage.encounter_set_image_id.is_(None), RemidioImage.download_error.isnot(None)),
        )
        .order_by(RemidioExam.exam_date.desc().nullslast(), RemidioImage.id.desc())
        .limit(50)
        .all()
    )
    report_rows = (
        db.query(RemidioReport, RemidioExam)
        .join(RemidioExam, RemidioExam.id == RemidioReport.remidio_exam_id)
        .filter(
            RemidioReport.remidio_exam_id.in_(exam_ids),
            or_(RemidioReport.encounter_set_attachment_id.is_(None), RemidioReport.download_error.isnot(None)),
        )
        .order_by(RemidioExam.exam_date.desc().nullslast(), RemidioReport.id.desc())
        .limit(50)
        .all()
    )
    assets: list[dict[str, Any]] = []
    for image, exam in image_rows:
        assets.append(_asset_status_row(exam, "Image", image.remidio_image_id, image.download_error, image.encounter_set_image_id))
    for report, exam in report_rows:
        assets.append(_asset_status_row(exam, report.report_type or "Report", report.remidio_report_id, report.download_error, report.encounter_set_attachment_id))
    return sorted(assets, key=lambda row: row["exam_date"] or "", reverse=True)[:50]


def _asset_status_row(exam: RemidioExam, asset_type: str, source_id: str, error: str | None, local_id: int | None) -> dict[str, Any]:
    return {
        "remidio_exam_id": exam.remidio_exam_id,
        "mrn": exam.remidio_patient_mrn,
        "exam_date": exam.exam_date,
        "site_custom_identifier": exam.site_custom_identifier,
        "asset_type": asset_type,
        "source_id": source_id,
        "status": "failed" if error else "pending" if local_id is None else "downloaded",
        "error": error,
    }


def _job_item_payload(item: JobItem) -> dict[str, Any]:
    try:
        data = json.loads(item.detail or "{}")
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("request"), dict):
        return data["request"]
    return data if isinstance(data, dict) else {}


def _job_item_result(item: JobItem) -> dict[str, Any]:
    try:
        data = json.loads(item.detail or "{}")
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        return data["result"]
    return {}


def _job_item_progress(item: JobItem) -> dict[str, Any] | None:
    try:
        data = json.loads(item.detail or "{}")
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and isinstance(data.get("progress"), dict):
        return data["progress"]
    return None


def _job_item_error(item: JobItem) -> str | None:
    try:
        data = json.loads(item.detail or "{}")
    except json.JSONDecodeError:
        return item.detail
    if isinstance(data, dict):
        return data.get("error")
    return None


def _result_summary(result: dict[str, Any]) -> dict[str, int]:
    summary = {
        "exams_seen": 0,
        "images_seen": 0,
        "images_downloaded": 0,
        "images_skipped": 0,
        "images_failed": 0,
        "images_pending": 0,
        "reports_seen": 0,
        "reports_downloaded": 0,
        "reports_skipped": 0,
        "reports_failed": 0,
        "reports_pending": 0,
        "encounters_created": 0,
        "encounters_reused": 0,
        "pending": 0,
        "failed": 0,
    }
    for group in result.get("groups") or []:
        pull_summary = ((group.get("pull") or {}).get("summary") or {})
        ingest_summary = (((group.get("ingest") or {}).get("summary")) or {})
        summary["exams_seen"] += int(pull_summary.get("exams_seen") or 0)
        summary["images_seen"] += int(pull_summary.get("images_seen") or 0)
        summary["reports_seen"] += int(pull_summary.get("reports_seen") or 0)
        summary["images_downloaded"] += int(ingest_summary.get("images_downloaded") or 0)
        summary["images_skipped"] += int(ingest_summary.get("images_skipped") or 0)
        summary["reports_downloaded"] += int(ingest_summary.get("reports_downloaded") or 0)
        summary["reports_skipped"] += int(ingest_summary.get("reports_skipped") or 0)
        summary["encounters_created"] += int(ingest_summary.get("encounters_created") or 0)
        summary["encounters_reused"] += int(ingest_summary.get("encounters_reused") or 0)
        summary["failed"] += int(ingest_summary.get("route_errors") or 0) + int(ingest_summary.get("download_errors") or 0)
        for exam in (((group.get("ingest") or {}).get("exams")) or []):
            for image in exam.get("images") or []:
                if image.get("status") in {"download_error", "no_route"}:
                    summary["images_failed"] += 1
            for report in exam.get("reports") or []:
                if report.get("status") in {"download_error", "no_route"}:
                    summary["reports_failed"] += 1
    summary["images_skipped"] = max(summary["images_skipped"] - summary["images_failed"], 0)
    summary["reports_skipped"] = max(summary["reports_skipped"] - summary["reports_failed"], 0)
    summary["images_pending"] = max(
        summary["images_seen"] - summary["images_downloaded"] - summary["images_skipped"] - summary["images_failed"],
        0,
    )
    summary["reports_pending"] = max(
        summary["reports_seen"] - summary["reports_downloaded"] - summary["reports_skipped"] - summary["reports_failed"],
        0,
    )
    summary["pending"] = summary["images_pending"] + summary["reports_pending"]
    return summary


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


def _parse_date(value: str) -> date:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise RemidioConfigError("Date values must be YYYY-MM-DD or DD-MM-YYYY.")


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
