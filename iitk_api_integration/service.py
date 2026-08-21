"""Project configuration, browsing, and idempotent IITK EncounterSet synchronization."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from encounter_set_types.models import EncounterSetType
from models import BASE_DIR, Camera, EncounterSetImage, Hospital, LabUnit, PatientEncounters, Project
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileEncounterSetType
from upload_profiles.service import manager_lab_unit_ids
from utils.encryption import decrypt_password_with_salt, encrypt_password_with_salt, generate_salt
from utils.image_processing import generate_thumbnail, get_thumbnail_filename, strip_exif_data
from utils.log_sanitize import sanitize_log_value

from .client import DEFAULT_BASE_URL, IITKClient
from .contracts import IITKImageDTO, IITKImageInventory, IITKSessionDTO
from .errors import IITKConfigError, IITKIntegrationError
from .models import IITKApiProjectConfig, IITKApiSessionLink


LOGGER = logging.getLogger("iitk_api_integration.service")
POSITION_ORDER = {"primary": 1, "up_left": 2, "up": 3, "up_right": 4, "right": 5, "down_right": 6, "down": 7, "down_left": 8, "left": 9, "composite": 10}
SYNC_STALE_AFTER = timedelta(minutes=15)
IST = timezone(timedelta(hours=5, minutes=30))
SITE_MAPPING_PATH = Path(__file__).with_name("site_mappings.json")


@dataclass(frozen=True)
class RuntimeConfig:
    id: int
    project_id: int
    lab_unit_id: int
    upload_profile_id: int
    encounter_set_type_id: int
    camera_id: int | None
    hospital_id: int | None
    base_url: str
    token: str
    site_filter: str | None
    sync_from_date: date | None
    last_success_at: datetime | None


@dataclass(frozen=True)
class SiteDestination:
    source_site: str | None
    effective_site: str | None
    status: str
    hospital_id: int | None
    lab_unit_id: int
    hospital_name: str | None
    lab_unit_name: str


@lru_cache(maxsize=1)
def _site_mapping_document() -> dict[str, Any]:
    body = json.loads(SITE_MAPPING_PATH.read_text(encoding="utf-8"))
    if not isinstance(body, dict):
        raise IITKConfigError("IITK site mapping JSON must contain an object.")
    return body


@lru_cache(maxsize=1)
def site_mapping_catalog() -> dict[str, dict[str, str]]:
    """Return the IITK-owned site map without database-specific identifiers."""
    sites = _site_mapping_document().get("sites")
    if not isinstance(sites, dict):
        raise IITKConfigError("IITK site mapping JSON is missing the sites object.")
    result: dict[str, dict[str, str]] = {}
    for raw_site, raw_target in sites.items():
        site = _normalized_site(raw_site)
        if not site or not isinstance(raw_target, dict):
            raise IITKConfigError("IITK site mapping JSON contains an invalid site entry.")
        hospital = str(raw_target.get("hospital") or "").strip()
        lab_unit = str(raw_target.get("lab_unit") or "").strip()
        if not hospital or not lab_unit:
            raise IITKConfigError("IITK site mapping JSON contains an incomplete destination.")
        result[site] = {"hospital": hospital, "lab_unit": lab_unit}
    return result


def project_connection_context(db: Session, project_id: int) -> dict[str, Any]:
    row = db.query(IITKApiProjectConfig).filter_by(project_id=project_id).one_or_none()
    derived = None
    readiness_error = None
    if row and row.active:
        try:
            derived = _derive_project_target(db, project_id)
        except IITKConfigError as exc:
            readiness_error = str(exc)
    return {
        "iitk_project_config": _config_payload(row) if row else {
            "project_id": project_id, "active": False, "token_configured": False,
            "last_attempt_at": None, "last_success_at": None, "last_error": None,
        },
        "iitk_project_target": derived,
        "iitk_project_readiness_error": readiness_error,
    }


def save_project_connection(db: Session, project_id: int, payload: dict[str, Any], *, manager_user_id: int) -> IITKApiProjectConfig | None:
    if db.get(Project, project_id) is None:
        raise IITKConfigError("The selected project was not found.")
    if not manager_lab_unit_ids(manager_user_id):
        raise IITKConfigError("You are not assigned to any lab units for project management.")
    row = db.query(IITKApiProjectConfig).filter_by(project_id=project_id).one_or_none()
    active = _bool(payload.get("active"), False)
    token = str(payload.get("api_token") or "").strip()
    if not active:
        if row:
            row.active = False
            row.updated_at = utcnow()
            db.flush()
        return row
    target = _derive_project_target(db, project_id)
    if row is None:
        if not token:
            raise IITKConfigError("IITK API token is required when enabling a project.")
        salt = generate_salt()
        row = IITKApiProjectConfig(
            project_id=project_id, lab_unit_id=target["lab_unit_id"],
            project_upload_profile_id=target["project_upload_profile_id"],
            encounter_set_type_id=target["encounter_set_type_id"], camera_id=target["camera_id"],
            base_url=DEFAULT_BASE_URL, api_token_encrypted=encrypt_password_with_salt(token, salt), secret_salt=salt,
        )
        db.add(row)
    else:
        row.lab_unit_id = target["lab_unit_id"]
        row.project_upload_profile_id = target["project_upload_profile_id"]
        row.encounter_set_type_id = target["encounter_set_type_id"]
        row.camera_id = target["camera_id"]
        if token:
            row.api_token_encrypted = encrypt_password_with_salt(token, row.secret_salt)
    row.active = True
    row.updated_at = utcnow()
    db.flush()
    return row


def site_mapping_payload(db: Session) -> list[dict[str, Any]]:
    """Describe static mappings and whether their named targets resolve locally."""
    rows = []
    for site, target in site_mapping_catalog().items():
        hospital, lab_unit = _named_site_target(db, target)
        rows.append({
            "site": site, "hospital": target["hospital"], "lab_unit": target["lab_unit"],
            "hospital_id": hospital.id if hospital else None, "lab_unit_id": lab_unit.id if lab_unit else None,
            "resolved": bool(hospital and lab_unit),
        })
    return rows


def list_configs(db: Session, *, manager_user_id: int | None = None) -> list[dict[str, Any]]:
    query = db.query(IITKApiProjectConfig).options(
        selectinload(IITKApiProjectConfig.project), selectinload(IITKApiProjectConfig.lab_unit),
        selectinload(IITKApiProjectConfig.project_profile).selectinload(ProjectUploadProfile.profile),
        selectinload(IITKApiProjectConfig.encounter_set_type), selectinload(IITKApiProjectConfig.camera),
    )
    if manager_user_id is not None:
        allowed = manager_lab_unit_ids(manager_user_id)
        query = query.filter(IITKApiProjectConfig.lab_unit_id.in_(allowed))
    return [_config_payload(row) for row in query.order_by(IITKApiProjectConfig.project_id).all()]


def save_config(db: Session, payload: dict[str, Any], *, manager_user_id: int) -> IITKApiProjectConfig:
    config_id = _optional_int(payload.get("id"))
    project_id = _required_int(payload, "project_id")
    lab_unit_id = _required_int(payload, "lab_unit_id")
    project_profile_id = _required_int(payload, "project_upload_profile_id")
    encounter_set_type_id = _required_int(payload, "encounter_set_type_id")
    allowed_units = manager_lab_unit_ids(manager_user_id)
    if lab_unit_id not in allowed_units:
        raise IITKConfigError("The selected lab unit is outside your management scope.")
    _validate_binding(db, project_id, lab_unit_id, project_profile_id, encounter_set_type_id)
    base_url = str(payload.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    token = str(payload.get("api_token") or "").strip()
    IITKClient(token or "validation-placeholder", base_url=base_url)
    row = db.get(IITKApiProjectConfig, config_id) if config_id else None
    if row is None:
        if not token:
            raise IITKConfigError("IITK API token is required for a new configuration.")
        salt = generate_salt()
        row = IITKApiProjectConfig(project_id=project_id, lab_unit_id=lab_unit_id, project_upload_profile_id=project_profile_id,
            encounter_set_type_id=encounter_set_type_id, base_url=base_url,
            api_token_encrypted=encrypt_password_with_salt(token, salt), secret_salt=salt)
        db.add(row)
    else:
        if row.lab_unit_id not in allowed_units:
            raise IITKConfigError("The IITK configuration is outside your management scope.")
        if row.project_id != project_id and row.sessions:
            raise IITKConfigError("A configuration with imported sessions cannot be moved to another project.")
        row.project_id = project_id
        row.lab_unit_id = lab_unit_id
        row.project_upload_profile_id = project_profile_id
        row.encounter_set_type_id = encounter_set_type_id
        row.base_url = base_url
        if token:
            row.api_token_encrypted = encrypt_password_with_salt(token, row.secret_salt)
    row.camera_id = _optional_int(payload.get("camera_id"))
    if row.camera_id is not None and db.get(Camera, row.camera_id) is None:
        raise IITKConfigError("The selected camera was not found.")
    row.site_filter = str(payload.get("site_filter") or "").strip() or None
    row.sync_from_date = _optional_date(payload.get("sync_from_date"))
    row.active = _bool(payload.get("active"), True)
    row.updated_at = utcnow()
    db.flush()
    return row


def get_config_payload(db: Session, config_id: int, *, manager_user_id: int) -> dict[str, Any]:
    rows = list_configs(db, manager_user_id=manager_user_id)
    return next((row for row in rows if row["id"] == config_id), None) or _raise_not_found()


def browse_sessions(config_id: int, *, manager_user_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    with get_db_session() as db:
        runtime = _runtime_config(db, config_id, manager_user_id=manager_user_id)
    page = IITKClient(runtime.token, base_url=runtime.base_url).list_sessions(
        site=filters.get("site") or runtime.site_filter, from_date=filters.get("from"), to_date=filters.get("to"),
        status=filters.get("status"), limit=min(max(_optional_int(filters.get("limit")) or 50, 1), 200),
        page_token=filters.get("pageToken"),
    )
    return {"sessions": [_session_api_payload(row) for row in page.sessions], "nextPageToken": page.next_page_token}


def sync_config(config_id: int, *, full: bool = False) -> dict[str, Any]:
    runtime = _begin_sync(config_id)
    if runtime is None:
        return {"config_id": config_id, "status": "skipped", "reason": "sync_already_running"}
    result = {"config_id": config_id, "status": "completed", "sessions_seen": 0, "encounters_created": 0,
              "encounters_updated": 0, "images_created": 0, "images_updated": 0, "images_unchanged": 0,
              "images_failed": 0, "failed": 0}
    try:
        client = IITKClient(runtime.token, base_url=runtime.base_url)
        sessions = _collect_sessions(client, runtime, full=full)
        result["sessions_seen"] = len(sessions)
        for session_dto in sessions.values():
            try:
                session_result = _sync_session(client, runtime, session_dto)
                for key in ("encounters_created", "encounters_updated", "images_created", "images_updated", "images_unchanged", "images_failed"):
                    result[key] += session_result[key]
                if session_result["images_failed"]:
                    result["failed"] += 1
            except Exception as exc:  # noqa: BLE001
                result["failed"] += 1
                _record_session_error(runtime.id, session_dto, exc)
                LOGGER.warning("IITK session sync failed config_id=%s session_ref=%s error=%s", runtime.id,
                    _opaque(session_dto.session_id), sanitize_log_value(exc), exc_info=True)
        if result["failed"]:
            result["status"] = "partial_error"
        _finish_sync(config_id, result=result)
        return result
    except Exception as exc:
        _finish_sync(config_id, error=exc)
        raise


def queue_active_config_syncs() -> dict[str, Any]:
    with get_db_session() as db:
        ids = [row[0] for row in db.execute(select(IITKApiProjectConfig.id).where(IITKApiProjectConfig.active.is_(True))).all()]
    queued = _queue_config_ids(ids)
    return {"queued": queued, "count": len(queued)}


def recover_stale_config_syncs(*, now: datetime | None = None) -> dict[str, Any]:
    """Reclaim stopped heartbeats, requeueing only during the IITK sync window."""
    checked_at = now or utcnow()
    reclaimed_ids = reclaim_stale_sync_locks(now=checked_at)
    queued = _queue_config_ids(reclaimed_ids) if _inside_scheduled_sync_window(checked_at) else []
    return {
        "reclaimed_config_ids": reclaimed_ids,
        "queued": queued,
        "count": len(queued),
        "deferred_count": len(reclaimed_ids) - len(queued),
    }


def _inside_scheduled_sync_window(now: datetime) -> bool:
    local = now.astimezone(IST)
    local_minute = local.hour * 60 + local.minute
    return 7 * 60 <= local_minute <= 18 * 60


def reclaim_stale_sync_locks(*, now: datetime | None = None) -> list[int]:
    cutoff = (now or utcnow()) - SYNC_STALE_AFTER
    with get_db_session() as db:
        rows = (
            db.query(IITKApiProjectConfig)
            .filter(
                IITKApiProjectConfig.active.is_(True),
                IITKApiProjectConfig.sync_started_at.is_not(None),
                IITKApiProjectConfig.sync_started_at < cutoff,
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        reclaimed_ids = [row.id for row in rows]
        for row in rows:
            row.sync_started_at = None
            row.updated_at = now or utcnow()
        db.commit()
    return reclaimed_ids


def _queue_config_ids(config_ids: list[int]) -> list[dict[str, Any]]:
    from celery_tasks.tasks.iitk_tasks import run_iitk_config_sync_task

    queued = []
    for config_id in config_ids:
        task = run_iitk_config_sync_task.delay(config_id, False)
        queued.append({"config_id": config_id, "task_id": task.id})
    return queued


def admin_context(db: Session, *, manager_user_id: int) -> dict[str, Any]:
    allowed = manager_lab_unit_ids(manager_user_id)
    project_profiles = db.query(ProjectUploadProfile).options(selectinload(ProjectUploadProfile.project), selectinload(ProjectUploadProfile.profile)).filter(ProjectUploadProfile.active.is_(True)).all()
    return {
        "iitk_configs": list_configs(db, manager_user_id=manager_user_id),
        "projects": db.query(Project).filter(Project.active.is_(True)).order_by(Project.title).all(),
        "lab_units": db.query(LabUnit).filter(LabUnit.id.in_(allowed)).order_by(LabUnit.name).all(),
        "project_profiles": project_profiles,
        "encounter_set_types": db.query(EncounterSetType).filter(EncounterSetType.active.is_(True)).order_by(EncounterSetType.name).all(),
        "cameras": db.query(Camera).order_by(Camera.name).all(),
        "iitk_site_mappings": site_mapping_payload(db),
        "default_base_url": DEFAULT_BASE_URL,
    }


def _collect_sessions(client: IITKClient, runtime: RuntimeConfig, *, full: bool) -> dict[str, IITKSessionDTO]:
    result: dict[str, IITKSessionDTO] = {}
    if full or runtime.last_success_at is None:
        filters = [{"from_date": runtime.sync_from_date.isoformat() if runtime.sync_from_date else None}]
    else:
        recent = (runtime.last_success_at.astimezone(timezone.utc).date() - timedelta(days=1))
        if runtime.sync_from_date and recent < runtime.sync_from_date:
            recent = runtime.sync_from_date
        filters = [{"from_date": recent.isoformat()}]
    for item in filters:
        page_token = None
        for _ in range(1000):
            page = client.list_sessions(site=runtime.site_filter, limit=200, page_token=page_token, **item)
            _touch_sync_heartbeat(runtime.id)
            result.update({row.session_id: row for row in page.sessions})
            page_token = page.next_page_token
            if not page_token:
                break
        else:
            raise IITKIntegrationError("IITK pagination exceeded the safety limit.")
    return result


def _sync_session(client: IITKClient, runtime: RuntimeConfig, session_dto: IITKSessionDTO) -> dict[str, int]:
    _touch_sync_heartbeat(runtime.id)
    inventory = client.list_images(session_dto.session_id)
    _touch_sync_heartbeat(runtime.id)
    for image in inventory.images:
        if image.position not in POSITION_ORDER:
            raise IITKIntegrationError("IITK inventory contains an unsupported image position.")
    current = _current_images(runtime.id, session_dto.session_id)
    downloaded: dict[str, bytes] = {}
    download_errors: list[str] = []
    for image in inventory.images:
        existing = current.get(image.position)
        if not existing or not existing.get("_stored_exists") or existing.get("source_size_bytes") != image.size_bytes or existing.get("source_captured_at") != image.captured_at:
            try:
                content = client.get_image(session_dto.session_id, image.filename)
                if image.size_bytes is not None and len(content) != image.size_bytes:
                    raise IITKIntegrationError("Downloaded IITK image size does not match the inventory.")
                downloaded[image.position] = content
            except Exception as exc:  # noqa: BLE001
                download_errors.append(f"{image.position}: {str(sanitize_log_value(exc))[:300]}")
            finally:
                _touch_sync_heartbeat(runtime.id)
    result = _persist_session(runtime, session_dto, inventory, downloaded)
    result["images_failed"] = len(download_errors)
    if download_errors:
        with get_db_session() as db:
            link = db.query(IITKApiSessionLink).filter_by(config_id=runtime.id, source_session_id=session_dto.session_id).one()
            link.last_error = "; ".join(download_errors)[:1000]
            db.add(link)
            db.commit()
    return result


def _persist_session(runtime: RuntimeConfig, source: IITKSessionDTO, inventory: IITKImageInventory, downloaded: dict[str, bytes]) -> dict[str, int]:
    counts = {"encounters_created": 0, "encounters_updated": 0, "images_created": 0, "images_updated": 0, "images_unchanged": 0, "images_failed": 0}
    now = utcnow()
    with get_db_session() as db:
        link = db.query(IITKApiSessionLink).filter_by(config_id=runtime.id, source_session_id=source.session_id).with_for_update().one_or_none()
        encounter = db.get(PatientEncounters, link.patient_encounter_id) if link else None
        capture_dt = _parse_datetime(source.started_at)
        effective_site = _effective_encounter_site(encounter, source.site)
        destination = _resolve_site_destination(db, runtime, source_site=source.site, effective_site=effective_site)
        metadata = _encounter_metadata(
            encounter.metadata_json if encounter else None,
            runtime,
            source,
            capture_dt,
            destination,
            now,
        )
        if encounter is None:
            encounter = PatientEncounters(uuid=str(uuid4()), name=f"IITK MRN {source.mrn}", patient_id=source.mrn,
                capture_date=capture_dt.date().isoformat(), capture_date_dt=capture_dt.date(), lab_unit_id=destination.lab_unit_id,
                project_id=runtime.project_id, upload_profile_id=runtime.upload_profile_id, is_set_based=True,
                encounter_verified_status="pending", metadata_json=metadata)
            db.add(encounter)
            db.flush()
            link = IITKApiSessionLink(config_id=runtime.id, source_session_id=source.session_id, patient_encounter_id=encounter.id,
                source_status=source.status, source_image_count=source.image_count, local_image_count=0,
                source_metadata_json=_source_audit_metadata(source, inventory))
            db.add(link)
            counts["encounters_created"] = 1
        else:
            encounter.name = f"IITK MRN {source.mrn}"
            encounter.patient_id = source.mrn
            encounter.capture_date = capture_dt.date().isoformat()
            encounter.capture_date_dt = capture_dt.date()
            encounter.lab_unit_id = destination.lab_unit_id
            encounter.metadata_json = metadata
            counts["encounters_updated"] = 1
        db.flush()
        images_by_position = {row.spatial_position: row for row in encounter.encounter_set_images}
        present_positions = {POSITION_ORDER[item.position] for item in inventory.images}
        for existing in images_by_position.values():
            image_meta = dict(existing.metadata_json or {})
            image_meta["source_present"] = existing.spatial_position in present_positions
            existing.metadata_json = image_meta
            existing.hospital_id = destination.hospital_id
        folder_rel = f"files/encounter_sets/{now.strftime('%Y_%m_%d')}/{encounter.id}"
        image_dir = BASE_DIR / folder_rel
        image_dir.mkdir(parents=True, exist_ok=True)
        for item in inventory.images:
            position = POSITION_ORDER[item.position]
            image = images_by_position.get(position)
            content = downloaded.get(item.position)
            if image is None:
                if content is None:
                    continue
                stored_filename = f"{uuid4()}.jpg"
                image = EncounterSetImage(uuid=str(uuid4()), patient_encounter_id=encounter.id, spatial_position=position,
                    original_filename=stored_filename, folder_rel=folder_rel, asset_kind="clinical_image", creates_task=False,
                    is_pii=False, visible_to_grader=True, project_id=runtime.project_id, hospital_id=destination.hospital_id,
                    camera_id=runtime.camera_id, created_at=now)
                db.add(image)
                images_by_position[position] = image
                counts["images_created"] += 1
            elif content is not None:
                counts["images_updated"] += 1
            else:
                counts["images_unchanged"] += 1
            if content is not None:
                safe_content = strip_exif_data(content)
                target = BASE_DIR / image.folder_rel / image.original_filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(safe_content)
                image.file_hash = hashlib.md5(safe_content).hexdigest()
                thumbnail = get_thumbnail_filename(image.original_filename)
                thumb_path = target.parent / "thumbnails" / thumbnail
                thumb_path.parent.mkdir(parents=True, exist_ok=True)
                image.thumbnail_filename = thumbnail if generate_thumbnail(target, thumb_path) else None
            image.metadata_json = {
                **(image.metadata_json or {}), "source_kind": "iitk_api", "source_session_ref": _opaque(source.session_id),
                "source_filename": item.filename,
                "source_filename_hash": hashlib.sha256(item.filename.encode()).hexdigest(), "source_size_bytes": item.size_bytes,
                "source_captured_at": item.captured_at,
                "source_captured_at_utc": _utc_iso_datetime(item.captured_at),
                "upstream_payload": item.raw_payload or _normalized_image_payload(item),
                "source_present": True, "gaze_position": item.position,
                "laterality": source.eye, "is_montage": item.position == "composite", "encounter_set_type_id": runtime.encounter_set_type_id,
            }
        inventory_hash = hashlib.sha256(json.dumps([(i.position, i.size_bytes, i.captured_at) for i in inventory.images], sort_keys=True).encode()).hexdigest()
        link.source_status = source.status
        link.source_image_count = source.image_count
        link.local_image_count = sum(1 for item in inventory.images if POSITION_ORDER[item.position] in images_by_position)
        link.inventory_hash = inventory_hash
        link.source_metadata_json = _source_audit_metadata(source, inventory)
        link.last_seen_at = now
        link.last_synced_at = now
        link.last_error = None
        config = db.get(IITKApiProjectConfig, runtime.id)
        if config and config.sync_started_at is not None:
            config.sync_started_at = now
            config.updated_at = now
        db.add_all([encounter, link])
        db.commit()
    return counts


def _source_audit_metadata(source: IITKSessionDTO, inventory: IITKImageInventory) -> dict[str, Any]:
    normalized = asdict(source)
    normalized.pop("raw_payload", None)
    return {
        **normalized,
        "upstream_session_payload": source.raw_payload or dict(normalized),
        "upstream_image_inventory_payload": inventory.raw_payload or {
            "sessionId": inventory.session_id,
            "mode": inventory.mode,
            "images": [_normalized_image_payload(item) for item in inventory.images],
        },
    }


def _normalized_image_payload(item: IITKImageDTO) -> dict[str, Any]:
    return {
        "filename": item.filename,
        "position": item.position,
        "sizeBytes": item.size_bytes,
        "contentType": item.content_type,
        "capturedAt": item.captured_at,
    }


def _current_images(config_id: int, source_session_id: str) -> dict[str, dict[str, Any]]:
    with get_db_session() as db:
        link = db.query(IITKApiSessionLink).filter_by(config_id=config_id, source_session_id=source_session_id).one_or_none()
        if link is None:
            return {}
        rows = db.query(EncounterSetImage).filter_by(patient_encounter_id=link.patient_encounter_id).all()
        result = {}
        for row in rows:
            metadata = dict(row.metadata_json or {})
            position = metadata.get("gaze_position")
            if position:
                metadata["_stored_exists"] = bool(row.folder_rel and row.original_filename and (BASE_DIR / row.folder_rel / row.original_filename).is_file())
                result[position] = metadata
        return result


def _encounter_metadata(
    existing: dict | None,
    runtime: RuntimeConfig,
    source: IITKSessionDTO,
    capture_dt: datetime,
    destination: SiteDestination,
    synced_at: datetime,
) -> dict:
    result = dict(existing or {})
    patient = dict(result.get("patient") if isinstance(result.get("patient"), dict) else {})
    patient.update({"hospital_UHID": source.mrn, "patient_age_yrs": source.age, "sex": source.gender})
    patient.setdefault("site_recruitment", destination.effective_site)
    result["patient"] = patient
    result["encounter"] = {**(result.get("encounter") if isinstance(result.get("encounter"), dict) else {}),
        "source_session_id": source.session_id,
        "capture_datetime": _utc_iso(capture_dt),
        "mode_capture": source.mode,
        "eye_laterality": source.eye, "patient_diagnosis": source.diagnosis,
        "patient_diagnosis_other": source.diagnosis_other, "captured_positions": list(source.captured_positions),
        "expected_positions": source.expected_positions, "capture_status": source.status, "clinician_uid": source.clinician_uid}
    existing_upload = dict(result.get("upload") if isinstance(result.get("upload"), dict) else {})
    source_site_first_seen = existing_upload.get("source_site", destination.source_site)
    result["upload"] = {**existing_upload,
        "source_kind": "iitk_api", "source_status": source.status, "source_image_count": source.image_count,
        "source_site": source_site_first_seen, "source_site_last_seen": destination.source_site,
        "site_mapping_status": destination.status,
        "mapped_hospital_id": destination.hospital_id, "mapped_lab_unit_id": destination.lab_unit_id,
        "encounter_set_type_id": runtime.encounter_set_type_id, "last_synced_at": synced_at.isoformat()}
    return result


def remap_iitk_encounter_site(db: Session, encounter: PatientEncounters) -> SiteDestination | None:
    """Apply an edited IITK site value immediately during verification."""
    metadata = encounter.metadata_json if isinstance(encounter.metadata_json, dict) else {}
    upload = metadata.get("upload") if isinstance(metadata.get("upload"), dict) else {}
    if upload.get("source_kind") != "iitk_api":
        return None
    link = db.query(IITKApiSessionLink).filter_by(patient_encounter_id=encounter.id).one_or_none()
    if link is None:
        return None
    runtime = _runtime_from_row(link.config, decrypt_token=False)
    source_site = _normalized_site(upload.get("source_site"))
    destination = _resolve_site_destination(
        db, runtime, source_site=source_site,
        effective_site=_effective_encounter_site(encounter, source_site),
    )
    old_lab_unit_id = encounter.lab_unit_id
    images = db.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).all()
    old_hospital_ids = sorted({image.hospital_id for image in images if image.hospital_id is not None})
    hospital_changed = any(image.hospital_id != destination.hospital_id for image in images)
    encounter.lab_unit_id = destination.lab_unit_id
    upload.update({
        "source_site": destination.source_site, "site_mapping_status": destination.status,
        "mapped_hospital_id": destination.hospital_id, "mapped_lab_unit_id": destination.lab_unit_id,
    })
    metadata["upload"] = upload
    encounter.metadata_json = metadata
    for image in images:
        image.hospital_id = destination.hospital_id
    if old_lab_unit_id != destination.lab_unit_id or hospital_changed:
        LOGGER.info(
            "IITK verification custody remap encounter_id=%s source_site=%s effective_site=%s "
            "old_lab_unit_id=%s new_lab_unit_id=%s old_hospital_ids=%s new_hospital_id=%s",
            encounter.id,
            sanitize_log_value(destination.source_site),
            sanitize_log_value(destination.effective_site),
            old_lab_unit_id,
            destination.lab_unit_id,
            old_hospital_ids,
            destination.hospital_id,
        )
    return destination


def _effective_encounter_site(encounter: PatientEncounters | None, source_site: str | None) -> str | None:
    if encounter and isinstance(encounter.metadata_json, dict):
        patient = encounter.metadata_json.get("patient")
        if isinstance(patient, dict) and "site_recruitment" in patient:
            return _normalized_site(patient.get("site_recruitment"))
    return _normalized_site(source_site)


def _resolve_site_destination(db: Session, runtime: RuntimeConfig, *, source_site: str | None,
                              effective_site: str | None) -> SiteDestination:
    normalized_source = _normalized_site(source_site)
    normalized_effective = _normalized_site(effective_site)
    target = site_mapping_catalog().get(normalized_effective or "")
    if target:
        hospital, lab_unit = _named_site_target(db, target)
        if hospital and lab_unit:
            return SiteDestination(normalized_source, normalized_effective, "mapped", hospital.id, lab_unit.id,
                                   hospital.name, lab_unit.name)
        LOGGER.warning("IITK site target is not present locally site=%s", sanitize_log_value(normalized_effective))
        status = "target_missing"
    else:
        status = "unmapped"
    fallback_lab = db.get(LabUnit, runtime.lab_unit_id)
    return SiteDestination(normalized_source, normalized_effective, status, runtime.hospital_id,
                           runtime.lab_unit_id, fallback_lab.hospital.name if fallback_lab and fallback_lab.hospital else None,
                           fallback_lab.name if fallback_lab else f"Lab unit {runtime.lab_unit_id}")


def _named_site_target(db: Session, target: dict[str, str]) -> tuple[Hospital | None, LabUnit | None]:
    hospital = db.query(Hospital).filter_by(name=target["hospital"]).one_or_none()
    if hospital is None:
        return None, None
    lab_unit = db.query(LabUnit).filter_by(hospital_id=hospital.id, name=target["lab_unit"]).one_or_none()
    return hospital, lab_unit


def _derive_project_target(db: Session, project_id: int) -> dict[str, Any]:
    mappings = (
        db.query(ProjectUploadProfile)
        .join(UploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .options(
            selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.encounter_set_type),
            selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.cameras),
        )
        .filter(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
        )
        .all()
    )
    targets = [
        (mapping, encounter_type)
        for mapping in mappings
        for encounter_type in mapping.profile.encounter_set_types
        if encounter_type.active and encounter_type.encounter_set_type and encounter_type.encounter_set_type.active
    ]
    iitk_targets = [
        target for target in targets
        if target[1].encounter_set_type.code.casefold() == "iitk-zips"
    ]
    selected_targets = iitk_targets or targets
    if not selected_targets:
        raise IITKConfigError("Configure an active Upload Profile and EncounterSetType for this project first.")
    if len(selected_targets) != 1:
        raise IITKConfigError(
            "The project's IITK EncounterSet target is ambiguous; configure exactly one IITK EncounterSetType target."
        )
    mapping, encounter_type = selected_targets[0]
    default_site = _normalized_site(_site_mapping_document().get("default_site"))
    default_target = site_mapping_catalog().get(default_site or "")
    if not default_target:
        raise IITKConfigError("IITK site mapping JSON does not define a valid default_site.")
    hospital, lab_unit = _named_site_target(db, default_target)
    if hospital is None or lab_unit is None:
        raise IITKConfigError("The IITK default hospital or lab unit is not present locally.")
    cameras = [row.camera for row in mapping.profile.cameras if row.camera]
    camera = cameras[0] if len(cameras) == 1 else None
    return {
        "project_upload_profile_id": mapping.id,
        "upload_profile_name": mapping.profile.name,
        "encounter_set_type_id": encounter_type.encounter_set_type_id,
        "encounter_set_type_name": encounter_type.encounter_set_type.name,
        "lab_unit_id": lab_unit.id, "lab_unit_name": lab_unit.name,
        "hospital_id": hospital.id, "hospital_name": hospital.name,
        "camera_id": camera.id if camera else None, "camera_name": camera.name if camera else None,
    }


def _normalized_site(value: Any) -> str | None:
    result = str(value).strip().casefold() if value not in {None, ""} else ""
    return result or None


def _begin_sync(config_id: int) -> RuntimeConfig | None:
    with get_db_session() as db:
        row = db.query(IITKApiProjectConfig).filter_by(id=config_id, active=True).with_for_update().one_or_none()
        if row is None:
            raise IITKConfigError("IITK project configuration was not found or inactive.")
        now = utcnow()
        if row.sync_started_at and row.sync_started_at > now - SYNC_STALE_AFTER:
            return None
        row.sync_started_at = now
        row.last_attempt_at = now
        row.last_error = None
        runtime = _runtime_from_row(row)
        db.add(row)
        db.commit()
        return runtime


def _finish_sync(config_id: int, *, result: dict | None = None, error: Exception | None = None) -> None:
    project_id = None
    with get_db_session() as db:
        row = db.get(IITKApiProjectConfig, config_id)
        if row:
            project_id = row.project_id
            row.sync_started_at = None
            if error is None:
                row.last_success_at = utcnow()
                row.last_error = None if not result or not result.get("failed") else f"{result['failed']} session(s) failed."
            else:
                row.last_error = str(sanitize_log_value(error))[:1000]
            row.updated_at = utcnow()
            db.add(row)
            db.commit()
    # Flip any cached field queue off "running" as soon as the sync ends, on the
    # failure path too - otherwise the app shows a fetch in progress forever.
    _bump_field_cache(project_id)


def _bump_field_cache(project_id: int | None) -> None:
    if project_id is None:
        return
    try:
        from app_cache import init_cache
        from field_workbench.cache import bump_project

        init_cache()
        bump_project(project_id)
    except Exception as exc:  # noqa: BLE001 - cache invalidation must not fail a sync
        LOGGER.warning("Field cache invalidation failed: %s", sanitize_log_value(exc))


def _touch_sync_heartbeat(config_id: int) -> None:
    with get_db_session() as db:
        row = db.get(IITKApiProjectConfig, config_id)
        if row and row.sync_started_at is not None:
            now = utcnow()
            row.sync_started_at = now
            row.updated_at = now
            db.commit()


def _record_session_error(config_id: int, source: IITKSessionDTO, exc: Exception) -> None:
    with get_db_session() as db:
        link = db.query(IITKApiSessionLink).filter_by(config_id=config_id, source_session_id=source.session_id).one_or_none()
        if link:
            link.last_error = str(sanitize_log_value(exc))[:1000]
            link.last_seen_at = utcnow()
            db.add(link)
            db.commit()


def _runtime_config(db: Session, config_id: int, *, manager_user_id: int) -> RuntimeConfig:
    row = db.get(IITKApiProjectConfig, config_id)
    if row is None or row.lab_unit_id not in manager_lab_unit_ids(manager_user_id):
        raise IITKConfigError("IITK project configuration was not found.")
    return _runtime_from_row(row)


def _runtime_from_row(row: IITKApiProjectConfig, *, decrypt_token: bool = True) -> RuntimeConfig:
    return RuntimeConfig(row.id, row.project_id, row.lab_unit_id, row.project_profile.upload_profile_id,
        row.encounter_set_type_id, row.camera_id, row.lab_unit.hospital_id if row.lab_unit else None, row.base_url,
        decrypt_password_with_salt(row.api_token_encrypted, row.secret_salt) if decrypt_token else "",
        row.site_filter, row.sync_from_date, row.last_success_at)


def _validate_binding(db: Session, project_id: int, lab_unit_id: int, project_profile_id: int, encounter_set_type_id: int) -> None:
    if db.get(Project, project_id) is None or db.get(LabUnit, lab_unit_id) is None:
        raise IITKConfigError("The selected project or lab unit was not found.")
    mapping = db.get(ProjectUploadProfile, project_profile_id)
    if mapping is None or mapping.project_id != project_id or not mapping.active:
        raise IITKConfigError("The selected upload profile is not active for this project.")
    attached = db.query(UploadProfileEncounterSetType).filter_by(upload_profile_id=mapping.upload_profile_id,
        encounter_set_type_id=encounter_set_type_id, active=True).first()
    if attached is None:
        raise IITKConfigError("The EncounterSetType is not active on the selected upload profile.")


def _config_payload(row: IITKApiProjectConfig) -> dict[str, Any]:
    return {"id": row.id, "project_id": row.project_id, "project_title": row.project.title if row.project else None,
        "lab_unit_id": row.lab_unit_id, "lab_unit_name": row.lab_unit.name if row.lab_unit else None,
        "project_upload_profile_id": row.project_upload_profile_id,
        "upload_profile_name": row.project_profile.profile.name if row.project_profile and row.project_profile.profile else None,
        "encounter_set_type_id": row.encounter_set_type_id,
        "encounter_set_type_name": row.encounter_set_type.name if row.encounter_set_type else None,
        "camera_id": row.camera_id, "camera_name": row.camera.name if row.camera else None, "base_url": row.base_url,
        "site_filter": row.site_filter, "sync_from_date": row.sync_from_date.isoformat() if row.sync_from_date else None,
        "active": row.active, "token_configured": bool(row.api_token_encrypted), "sync_running": bool(row.sync_started_at),
        "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
        "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None, "last_error": row.last_error}


def _session_api_payload(row: IITKSessionDTO) -> dict[str, Any]:
    return {"sessionId": row.session_id, "site": row.site, "mode": row.mode, "startedAt": row.started_at,
        "capturedPositions": list(row.captured_positions), "expectedPositions": row.expected_positions,
        "status": row.status, "imageCount": row.image_count, "mrn": row.mrn, "age": row.age, "eye": row.eye,
        "gender": row.gender, "diagnosis": row.diagnosis, "diagnosisOther": row.diagnosis_other}


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IITKIntegrationError("IITK startedAt is not a valid ISO datetime.") from exc
    aware = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc)


def _utc_iso_datetime(value: str | None) -> str | None:
    return _utc_iso(_parse_datetime(value)) if value else None


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = _optional_int(payload.get(key))
    if value is None:
        raise IITKConfigError(f"{key} is required.")
    return value


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _optional_date(value: Any) -> date | None:
    if value in {None, ""}:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise IITKConfigError("sync_from_date must use YYYY-MM-DD.") from exc


def _bool(value: Any, default: bool) -> bool:
    if value in {None, ""}:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _opaque(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _raise_not_found():
    raise IITKConfigError("IITK project configuration was not found.")
