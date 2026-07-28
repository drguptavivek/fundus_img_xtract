"""IIT Kottayam EncounterSet ZIP importer."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from sqlalchemy.orm import Session as OrmSession

from auth.utils import utcnow
from encounter_sets.models import EncounterSetAttachment
from models import BASE_DIR, PROCESSING_ERROR_DIR, PROCESSED_DIR, PatientEncounters, ZipFile, EncounterSetImage
from upload_profiles.models import PatientEncounterTargetDisease
from utils.image_processing import generate_thumbnail, get_thumbnail_filename, strip_exif_data
from utils.log_sanitize import sanitize_log_value

import logging

logger = logging.getLogger(__name__)


ALLOWED_EXTS = {".jpg", ".jpeg", ".json"}
IITK_FOLDER_RE = re.compile(r"^MRN(?P<mrn>[A-Za-z0-9]+)_(?P<date>\d{8})_(?P<suffix>[A-Za-z0-9]+)$")
POSITION_ORDER = {
    "primary": 1,
    "up_left": 2,
    "up": 3,
    "up_right": 4,
    "right": 5,
    "down_right": 6,
    "down": 7,
    "down_left": 8,
    "left": 9,
    "composite": 10,
}


class IITKZipImportError(ValueError):
    """Raised when an IITK ZIP does not match the expected EncounterSet format."""


@dataclass(frozen=True)
class IITKEncounterFolder:
    folder: PurePosixPath
    mrn: str
    capture_date: str
    suffix: str
    metadata_member: zipfile.ZipInfo
    image_members: tuple[zipfile.ZipInfo, ...]
    metadata: dict


def ingest_iitk_encounterset_zip(zip_path: Path, session: OrmSession, upload_context: dict | None = None) -> dict:
    """Ingest an IIT Kottayam strabismus ZIP containing multiple EncounterSet folders."""
    if not zipfile.is_zipfile(zip_path):
        raise IITKZipImportError("Not a valid ZIP file")

    upload_context = dict(upload_context or {})
    md5_hash = _calculate_md5(zip_path)
    existing = session.query(ZipFile).filter_by(md5_hash=md5_hash).first()
    if existing:
        _move_zip_quietly(zip_path, _daily_dir(PROCESSED_DIR) / "dupmd5" / zip_path.name)
        return {
            "patient_encounter_ids": [],
            "patient_encounter_id": None,
            "encounter_set_image_ids": [],
            "encounter_set_attachment_ids": [],
            "status": "duplicate",
        }

    required = ("lab_unit_id", "project_id")
    missing = [key for key in required if not upload_context.get(key)]
    if missing:
        raise IITKZipImportError(f"IITK ZIP upload metadata is missing required scope: {', '.join(missing)}")

    encounter_ids: list[int] = []
    image_ids: list[int] = []
    attachment_ids: list[int] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            folders = _discover_iitk_folders(archive)
            if not folders:
                raise IITKZipImportError("IITK ZIP contains no MRN*_YYYYMMDD_* encounter folders.")

            zip_file = ZipFile(zip_filename=_clean_filename(zip_path.name), md5_hash=md5_hash)
            session.add(zip_file)
            session.flush()

            for folder in folders:
                encounter = _create_encounter(
                    session=session,
                    zip_file=zip_file,
                    folder=folder,
                    zip_path=zip_path,
                    upload_context=upload_context,
                )
                encounter_ids.append(encounter.id)
                image_ids.extend(
                    _create_images(
                        session=session,
                        archive=archive,
                        encounter=encounter,
                        folder=folder,
                        zip_path=zip_path,
                        upload_context=upload_context,
                    )
                )
                attachment_ids.append(
                    _create_metadata_attachment(
                        session=session,
                        archive=archive,
                        encounter=encounter,
                        folder=folder,
                        zip_path=zip_path,
                        upload_context=upload_context,
                    )
                )

            session.commit()
            processed_path = _daily_dir(PROCESSED_DIR) / zip_path.name
            processed_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(zip_path), str(processed_path))
            return {
                "patient_encounter_ids": encounter_ids,
                "patient_encounter_id": encounter_ids[0] if len(encounter_ids) == 1 else None,
                "encounter_set_image_ids": image_ids,
                "encounter_set_attachment_ids": attachment_ids,
                "status": "ok",
            }
    except Exception:
        session.rollback()
        error_path = _daily_dir(PROCESSING_ERROR_DIR) / zip_path.name
        error_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(zip_path), str(error_path))
        except Exception as exc:
            logger.error(
                "Failed to move errored IITK ZIP %s: %s",
                sanitize_log_value(zip_path.name),
                sanitize_log_value(exc),
                exc_info=True,
            )
        raise


def _discover_iitk_folders(archive: zipfile.ZipFile) -> list[IITKEncounterFolder]:
    by_folder: dict[PurePosixPath, list[zipfile.ZipInfo]] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        path = _safe_member_path(info.filename)
        if path is None:
            continue
        if path.suffix.lower() not in ALLOWED_EXTS:
            raise IITKZipImportError(f"Disallowed IITK ZIP file extension: {info.filename}")
        if path.suffix.lower() in {".jpg", ".jpeg"} and _sniff_member_type(archive, info) != "jpg":
            raise IITKZipImportError(f"Type mismatch (expected JPG): {info.filename}")
        by_folder.setdefault(path.parent, []).append(info)

    folders: list[IITKEncounterFolder] = []
    for folder, members in by_folder.items():
        match = IITK_FOLDER_RE.match(folder.name)
        if not match:
            continue
        metadata_members = [info for info in members if PurePosixPath(info.filename).suffix.lower() == ".json"]
        if len(metadata_members) != 1:
            raise IITKZipImportError(f"IITK encounter folder must contain one metadata JSON: {folder}")
        image_members = tuple(
            sorted(
                [info for info in members if PurePosixPath(info.filename).suffix.lower() in {".jpg", ".jpeg"}],
                key=lambda info: (_position_from_filename(PurePosixPath(info.filename).stem), info.filename),
            )
        )
        if not image_members:
            raise IITKZipImportError(f"IITK encounter folder contains no JPG images: {folder}")
        metadata = _read_metadata(archive, metadata_members[0])
        folders.append(
            IITKEncounterFolder(
                folder=folder,
                mrn=str(metadata.get("mrn") or match.group("mrn")),
                capture_date=_capture_date_from_metadata(metadata, match.group("date")),
                suffix=match.group("suffix"),
                metadata_member=metadata_members[0],
                image_members=image_members,
                metadata=metadata,
            )
        )
    return sorted(folders, key=lambda item: (item.capture_date, item.mrn, str(item.folder)))


def _create_encounter(
    *,
    session: OrmSession,
    zip_file: ZipFile,
    folder: IITKEncounterFolder,
    zip_path: Path,
    upload_context: dict,
) -> PatientEncounters:
    target_disease_ids = [int(value) for value in upload_context.get("target_disease_ids") or []]
    metadata = folder.metadata
    encounter = PatientEncounters(
        name=f"MRN{folder.mrn}",
        patient_id=folder.mrn,
        capture_date=folder.capture_date,
        capture_date_dt=_parse_capture_date(folder.capture_date),
        lab_unit_id=int(upload_context["lab_unit_id"]),
        project_id=int(upload_context["project_id"]),
        upload_profile_id=_optional_int(upload_context.get("upload_profile_id")),
        disease_id=target_disease_ids[0] if len(target_disease_ids) == 1 else None,
        is_set_based=True,
        metadata_json={
            "source_kind": "iitk_zip",
            "source_identity": "iitk_metadata_json",
            "source_zip_filename": zip_path.name,
            "source_patient_folder": str(folder.folder),
            "source_session_id": metadata.get("sessionId"),
            "site": metadata.get("site"),
            "age": metadata.get("age"),
            "gender": metadata.get("gender"),
            "eye": metadata.get("eye"),
            "diagnosis": metadata.get("diagnosis"),
            "mode": metadata.get("mode"),
            "started_at": metadata.get("startedAt"),
            "clinician_uid": metadata.get("clinicianUid"),
            "captured_positions": metadata.get("capturedPositions") or [],
        },
    )
    zip_file.patient_encounter = encounter if zip_file.patient_encounter is None else zip_file.patient_encounter
    session.add(encounter)
    session.flush()
    if zip_file.patient_encounter is not encounter:
        encounter.zip_file_id = None
    for disease_id in target_disease_ids:
        session.add(PatientEncounterTargetDisease(patient_encounter_id=encounter.id, disease_id=disease_id, is_default=False))
    session.flush()
    return encounter


def _create_images(
    *,
    session: OrmSession,
    archive: zipfile.ZipFile,
    encounter: PatientEncounters,
    folder: IITKEncounterFolder,
    zip_path: Path,
    upload_context: dict,
) -> list[int]:
    folder_rel = f"files/encounter_sets/{utcnow().strftime('%Y_%m_%d')}/{encounter.id}"
    image_dir = BASE_DIR / folder_rel
    image_dir.mkdir(parents=True, exist_ok=True)
    image_ids: list[int] = []
    used_positions: set[int] = set()
    for member in folder.image_members:
        source_path = PurePosixPath(member.filename)
        gaze_position = _position_from_filename(source_path.stem)
        spatial_position = POSITION_ORDER.get(gaze_position)
        if spatial_position is None:
            raise IITKZipImportError(f"Unknown IITK gaze position in filename: {member.filename}")
        if spatial_position in used_positions:
            raise IITKZipImportError(f"Duplicate IITK gaze position {gaze_position}: {folder.folder}")
        used_positions.add(spatial_position)
        ext = source_path.suffix.lower()
        stored_filename = f"{uuid4()}{ext}"
        target_path = image_dir / stored_filename
        with archive.open(member) as source:
            content = source.read()
        safe_content = strip_exif_data(content)
        target_path.write_bytes(safe_content)
        thumbnail_filename = _generate_thumbnail(target_path, stored_filename)
        image = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=spatial_position,
            original_filename=stored_filename,
            folder_rel=folder_rel,
            file_hash=hashlib.md5(safe_content).hexdigest(),
            asset_kind="clinical_image",
            creates_task=True,
            is_pii=False,
            visible_to_grader=True,
            project_id=_optional_int(upload_context.get("project_id")),
            camera_id=_optional_int(upload_context.get("camera_id")),
            hospital_id=_optional_int(upload_context.get("hospital_id")),
            thumbnail_filename=thumbnail_filename,
            metadata_json={
                "source_kind": "iitk_zip",
                "source_zip_filename": zip_path.name,
                "source_path": str(source_path),
                "source_folder": str(source_path.parent),
                "source_session_id": folder.metadata.get("sessionId"),
                "gaze_position": gaze_position,
                "eye": folder.metadata.get("eye"),
                "diagnosis": folder.metadata.get("diagnosis"),
            },
            created_at=utcnow(),
        )
        session.add(image)
        session.flush()
        image_ids.append(image.id)
    return image_ids


def _create_metadata_attachment(
    *,
    session: OrmSession,
    archive: zipfile.ZipFile,
    encounter: PatientEncounters,
    folder: IITKEncounterFolder,
    zip_path: Path,
    upload_context: dict,
) -> int:
    attachment_dir_rel = f"files/encounter_sets/{utcnow().strftime('%Y_%m_%d')}/{encounter.id}/attachments"
    attachment_dir = BASE_DIR / attachment_dir_rel
    attachment_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4()}.json"
    target_path = attachment_dir / stored_filename
    with archive.open(folder.metadata_member) as source:
        content = source.read()
    target_path.write_bytes(content)
    attachment = EncounterSetAttachment(
        patient_encounter_id=encounter.id,
        uuid=str(uuid4()),
        asset_kind="document",
        original_filename=PurePosixPath(folder.metadata_member.filename).name,
        stored_filename=stored_filename,
        folder_rel=attachment_dir_rel,
        mime_type="application/json",
        file_size_bytes=len(content),
        file_hash=hashlib.md5(content).hexdigest(),
        is_pii=True,
        visible_to_grader=False,
        creates_task=False,
        project_id=_optional_int(upload_context.get("project_id")),
        upload_profile_id=_optional_int(upload_context.get("upload_profile_id")),
        hospital_id=_optional_int(upload_context.get("hospital_id")),
        metadata_json={
            "source_kind": "iitk_zip",
            "source_zip_filename": zip_path.name,
            "source_path": folder.metadata_member.filename,
            "document_type": "iitk_metadata_json",
        },
        created_at=utcnow(),
    )
    session.add(attachment)
    session.flush()
    return attachment.id


def _safe_member_path(filename: str) -> PurePosixPath | None:
    if filename.startswith("/") or filename.startswith("\\"):
        raise IITKZipImportError(f"Path traversal detected: {filename}")
    path = PurePosixPath(filename)
    if any(part in {"..", ""} for part in path.parts):
        raise IITKZipImportError(f"Path traversal detected: {filename}")
    if path.name.startswith("._") or path.parts[0] == "__MACOSX":
        return None
    return path


def _read_metadata(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict:
    with archive.open(info) as source:
        data = json.loads(source.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise IITKZipImportError(f"IITK metadata must be a JSON object: {info.filename}")
    return data


def _capture_date_from_metadata(metadata: dict, fallback_yyyymmdd: str) -> str:
    started_at = str(metadata.get("startedAt") or "")
    if len(started_at) >= 10:
        return started_at[:10]
    return f"{fallback_yyyymmdd[:4]}-{fallback_yyyymmdd[4:6]}-{fallback_yyyymmdd[6:8]}"


def _position_from_filename(stem: str) -> str:
    parts = stem.split("_")
    if len(parts) < 3:
        return ""
    return "_".join(parts[2:])


def _parse_capture_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _sniff_member_type(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    with archive.open(info) as source:
        head = source.read(8)
    if len(head) >= 3 and head[:3] == b"\xFF\xD8\xFF":
        return "jpg"
    return "unknown"


def _generate_thumbnail(image_path: Path, filename: str) -> str | None:
    try:
        thumbnail_filename = get_thumbnail_filename(filename)
        thumbnail_dir = image_path.parent / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        if generate_thumbnail(image_path, thumbnail_dir / thumbnail_filename):
            return thumbnail_filename
    except Exception as exc:
        logger.info("IITK ZIP thumbnail generation failed: %s", sanitize_log_value(exc))
    return None


def _calculate_md5(filepath: Path) -> str:
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def _clean_filename(name: str) -> str:
    return re.sub(r"\s\(\d+\)", "", name)


def _daily_dir(root: Path) -> Path:
    return root / datetime.now().strftime("%Y_%m_%d")


def _move_zip_quietly(source: Path, target: Path) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
    except Exception:
        pass


def _optional_int(value) -> int | None:
    return int(value) if value not in (None, "") else None
