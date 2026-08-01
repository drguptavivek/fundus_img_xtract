"""Project configuration, browsing, and idempotent IITK EncounterSet synchronization."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from encounter_set_types.models import EncounterSetType
from models import BASE_DIR, Camera, EncounterSetImage, LabUnit, PatientEncounters, Project
from upload_profiles.models import ProjectUploadProfile, UploadProfileEncounterSetType
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
SYNC_STALE_AFTER = timedelta(hours=2)


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
    from celery_tasks.tasks.iitk_tasks import run_iitk_config_sync_task

    with get_db_session() as db:
        ids = [row[0] for row in db.execute(select(IITKApiProjectConfig.id).where(IITKApiProjectConfig.active.is_(True))).all()]
    queued = []
    for config_id in ids:
        task = run_iitk_config_sync_task.delay(config_id, False)
        queued.append({"config_id": config_id, "task_id": task.id})
    return {"queued": queued, "count": len(queued)}


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
            result.update({row.session_id: row for row in page.sessions})
            page_token = page.next_page_token
            if not page_token:
                break
        else:
            raise IITKIntegrationError("IITK pagination exceeded the safety limit.")
    return result


def _sync_session(client: IITKClient, runtime: RuntimeConfig, session_dto: IITKSessionDTO) -> dict[str, int]:
    inventory = client.list_images(session_dto.session_id)
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
        metadata = _encounter_metadata(encounter.metadata_json if encounter else None, runtime, source, now)
        if encounter is None:
            encounter = PatientEncounters(uuid=str(uuid4()), name=f"IITK MRN {source.mrn}", patient_id=source.mrn,
                capture_date=capture_dt.date().isoformat(), capture_date_dt=capture_dt.date(), lab_unit_id=runtime.lab_unit_id,
                project_id=runtime.project_id, upload_profile_id=runtime.upload_profile_id, is_set_based=True,
                encounter_verified_status="pending", metadata_json=metadata)
            db.add(encounter)
            db.flush()
            link = IITKApiSessionLink(config_id=runtime.id, source_session_id=source.session_id, patient_encounter_id=encounter.id,
                source_status=source.status, source_image_count=source.image_count, local_image_count=0, source_metadata_json=asdict(source))
            db.add(link)
            counts["encounters_created"] = 1
        else:
            encounter.name = f"IITK MRN {source.mrn}"
            encounter.patient_id = source.mrn
            encounter.capture_date = capture_dt.date().isoformat()
            encounter.capture_date_dt = capture_dt.date()
            encounter.metadata_json = metadata
            counts["encounters_updated"] = 1
        db.flush()
        images_by_position = {row.spatial_position: row for row in encounter.encounter_set_images}
        present_positions = {POSITION_ORDER[item.position] for item in inventory.images}
        for existing in images_by_position.values():
            image_meta = dict(existing.metadata_json or {})
            image_meta["source_present"] = existing.spatial_position in present_positions
            existing.metadata_json = image_meta
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
                    is_pii=False, visible_to_grader=True, project_id=runtime.project_id, hospital_id=runtime.hospital_id,
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
                "source_filename_hash": hashlib.sha256(item.filename.encode()).hexdigest(), "source_size_bytes": item.size_bytes,
                "source_captured_at": item.captured_at, "source_present": True, "gaze_position": item.position,
                "laterality": source.eye, "is_montage": item.position == "composite", "encounter_set_type_id": runtime.encounter_set_type_id,
            }
        inventory_hash = hashlib.sha256(json.dumps([(i.position, i.size_bytes, i.captured_at) for i in inventory.images], sort_keys=True).encode()).hexdigest()
        link.source_status = source.status
        link.source_image_count = source.image_count
        link.local_image_count = sum(1 for item in inventory.images if POSITION_ORDER[item.position] in images_by_position)
        link.inventory_hash = inventory_hash
        link.source_metadata_json = asdict(source)
        link.last_seen_at = now
        link.last_synced_at = now
        link.last_error = None
        db.add_all([encounter, link])
        db.commit()
    return counts


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


def _encounter_metadata(existing: dict | None, runtime: RuntimeConfig, source: IITKSessionDTO, synced_at: datetime) -> dict:
    result = dict(existing or {})
    result["patient"] = {**(result.get("patient") if isinstance(result.get("patient"), dict) else {}),
        "hospital_UHID": source.mrn, "patient_age_yrs": source.age, "sex": source.gender, "site_recruitment": source.site}
    result["encounter"] = {**(result.get("encounter") if isinstance(result.get("encounter"), dict) else {}),
        "source_session_id": source.session_id, "capture_datetime": source.started_at, "mode_capture": source.mode,
        "eye_laterality": source.eye, "patient_diagnosis": source.diagnosis,
        "patient_diagnosis_other": source.diagnosis_other, "captured_positions": list(source.captured_positions),
        "expected_positions": source.expected_positions, "capture_status": source.status, "clinician_uid": source.clinician_uid}
    result["upload"] = {**(result.get("upload") if isinstance(result.get("upload"), dict) else {}),
        "source_kind": "iitk_api", "source_status": source.status, "source_image_count": source.image_count,
        "encounter_set_type_id": runtime.encounter_set_type_id, "last_synced_at": synced_at.isoformat()}
    return result


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
    with get_db_session() as db:
        row = db.get(IITKApiProjectConfig, config_id)
        if row:
            row.sync_started_at = None
            if error is None:
                row.last_success_at = utcnow()
                row.last_error = None if not result or not result.get("failed") else f"{result['failed']} session(s) failed."
            else:
                row.last_error = str(sanitize_log_value(error))[:1000]
            row.updated_at = utcnow()
            db.add(row)
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


def _runtime_from_row(row: IITKApiProjectConfig) -> RuntimeConfig:
    return RuntimeConfig(row.id, row.project_id, row.lab_unit_id, row.project_profile.upload_profile_id,
        row.encounter_set_type_id, row.camera_id, row.lab_unit.hospital_id if row.lab_unit else None, row.base_url,
        decrypt_password_with_salt(row.api_token_encrypted, row.secret_salt), row.site_filter, row.sync_from_date, row.last_success_at)


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
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
