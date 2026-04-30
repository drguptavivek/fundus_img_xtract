"""Use cases for configuring and pulling Remidio API data."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from models import (
    Camera,
    Disease,
    LabUnit,
    Project,
    RemidioConnection,
    RemidioRoutingRule,
    RemidioSite,
)
from utils.encryption import decrypt_password_with_salt, encrypt_password_with_salt, generate_salt

from .client import RemidioClient
from .errors import RemidioConfigError
from .ingest import ingest_staged_files
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
        active=bool(payload.get("active", True)),
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
    if "client_identification_token" in payload:
        connection.client_identification_token_encrypted = encrypt_password_with_salt(
            _required_string(payload, "client_identification_token"),
            connection.secret_salt,
        )
    if "email" in payload:
        connection.email_encrypted = encrypt_password_with_salt(_required_string(payload, "email"), connection.secret_salt)
    if "password" in payload:
        connection.password_encrypted = encrypt_password_with_salt(_required_string(payload, "password"), connection.secret_salt)
    if "active" in payload:
        connection.active = bool(payload["active"])
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
        site.active = bool(payload["active"])
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

    site_custom_identifier = (payload.get("site_custom_identifier") or (site.site_custom_identifier if site else None) or "").strip()
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
    rule.active = bool(payload.get("active", True))
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


def _secrets(connection: RemidioConnection) -> RemidioSecrets:
    return RemidioSecrets(
        base_url=connection.base_url,
        client_name=connection.client_name,
        client_identification_token=decrypt_password_with_salt(connection.client_identification_token_encrypted, connection.secret_salt),
        email=decrypt_password_with_salt(connection.email_encrypted, connection.secret_salt),
        password=decrypt_password_with_salt(connection.password_encrypted, connection.secret_salt),
    )


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


def _normalize_base_url(value: str) -> str:
    normalized = str(value).strip().rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise RemidioConfigError("base_url must start with http:// or https://.")
    return normalized


def _iso(value) -> str | None:
    return value.isoformat() if value else None
