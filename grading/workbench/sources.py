"""Authoritative task source, profile-lineage, and media resolution."""

from __future__ import annotations

from dataclasses import dataclass

from models import EncounterFile, EncounterSetImage, GradingTask, ImageMetadata
from upload_profiles.models import UploadProfile

from .contracts import WorkbenchMediaDTO, WorkbenchSourceDTO
from .errors import WorkbenchError


class InvalidTaskSource(WorkbenchError):
    code = "invalid_task_source"


@dataclass(frozen=True)
class ResolvedTaskSource:
    source: WorkbenchSourceDTO
    media: WorkbenchMediaDTO | None


def resolve_task_source(db, task: GradingTask) -> ResolvedTaskSource:
    refs = [
        task.encounter_file is not None,
        task.direct_image is not None,
        task.encounter_set_image is not None,
        task.patient_encounter is not None,
    ]
    if sum(refs) != 1:
        raise InvalidTaskSource("A grading task must resolve to exactly one source target.")

    profile_id = task.source_upload_profile_id
    profile_lineage = "exact" if profile_id is not None else "legacy_unprofiled"
    project_id: int | None = None
    media: WorkbenchMediaDTO | None = None

    if task.encounter_file is not None:
        item = task.encounter_file
        encounter = item.patient_encounter
        inherited = encounter.upload_profile_id if encounter else None
        profile_id, profile_lineage = _lineage(profile_id, inherited)
        project_id = item.project_id or (encounter.project_id if encounter else None)
        media = _media(db, "encounter_file", item.uuid, item.eye_side)
    elif task.direct_image is not None:
        item = task.direct_image
        project_id = item.project_id
        media = _media(db, "direct_image_upload", item.uuid, None)
    elif task.encounter_set_image is not None:
        item = task.encounter_set_image
        encounter = item.patient_encounter
        inherited = encounter.upload_profile_id if encounter else None
        profile_id, profile_lineage = _lineage(profile_id, inherited)
        project_id = item.project_id or (encounter.project_id if encounter else None)
        laterality = _metadata_laterality(item.metadata_json)
        media = _media(db, "encounter_set_image", item.uuid, laterality)
    else:
        encounter = task.patient_encounter
        inherited = encounter.upload_profile_id if encounter else None
        profile_id, profile_lineage = _lineage(profile_id, inherited)
        project_id = encounter.project_id if encounter else None

    if profile_lineage == "invalid":
        raise InvalidTaskSource("The task upload-profile lineage conflicts with its source encounter.")

    return ResolvedTaskSource(
        source=WorkbenchSourceDTO(
            source_type=media.source_type if media else "patient_encounter",
            profile_id=profile_id,
            profile_lineage=profile_lineage,
            project_id=project_id,
            lab_unit_id=task.lab_unit_id,
            profile=_profile_snapshot(db, profile_id),
        ),
        media=media,
    )


def resolve_encounter_evidence(db, task: GradingTask) -> tuple[WorkbenchMediaDTO, ...]:
    """Return permitted real images for an encounter target without faking media ownership."""
    if task.patient_encounter_id is None:
        return ()
    encounter_files = (
        db.query(EncounterFile)
        .filter(EncounterFile.patient_encounter_id == task.patient_encounter_id)
        .order_by(EncounterFile.id)
        .all()
    )
    encounter_set_images = (
        db.query(EncounterSetImage)
        .filter(
            EncounterSetImage.patient_encounter_id == task.patient_encounter_id,
            EncounterSetImage.visible_to_grader.is_(True),
        )
        .order_by(EncounterSetImage.spatial_position, EncounterSetImage.id)
        .all()
    )
    evidence = [
        _media(db, "encounter_file", item.uuid, item.eye_side)
        for item in encounter_files
        if item.uuid
    ]
    evidence.extend(
        _media(
            db,
            "encounter_set_image",
            item.uuid,
            _metadata_laterality(item.metadata_json),
        )
        for item in encounter_set_images
        if item.uuid
    )
    return tuple(evidence)


def _lineage(explicit: int | None, inherited: int | None) -> tuple[int | None, str]:
    if explicit is not None:
        if inherited is not None and explicit != inherited:
            return explicit, "invalid"
        return explicit, "exact"
    if inherited is not None:
        return inherited, "inherited"
    return None, "legacy_unprofiled"


def _media(db, source_type: str, image_uuid: str | None, laterality: str | None) -> WorkbenchMediaDTO:
    if not image_uuid:
        raise InvalidTaskSource("The task source does not have an image UUID.")
    metadata = (
        db.query(ImageMetadata)
        .filter(ImageMetadata.image_uuid == image_uuid, ImageMetadata.image_variant == "orig")
        .first()
    )
    return WorkbenchMediaDTO(
        source_type=source_type,
        image_uuid=image_uuid,
        media_url=f"/media/img/{image_uuid}",
        thumbnail_url=f"/media/img/{image_uuid}/thumbnail",
        laterality=laterality,
        width=metadata.width if metadata else None,
        height=metadata.height if metadata else None,
        metadata={
            "format": metadata.format if metadata else None,
            "mode": metadata.mode if metadata else None,
        },
    )


def _metadata_laterality(metadata: dict | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("laterality") or metadata.get("eye_side")
    return str(value) if value not in (None, "") else None


def _profile_snapshot(db, profile_id: int | None) -> dict | None:
    if profile_id is None:
        return None
    profile = db.get(UploadProfile, profile_id)
    if profile is None:
        raise InvalidTaskSource("The task upload profile no longer exists.")
    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "active": profile.active,
        "task_prioritization": profile.task_prioritization_json or {},
        "disease_ids": sorted(item.disease_id for item in profile.diseases),
        "upload_kinds": sorted(item.upload_kind for item in profile.upload_kinds),
        "encounter_set_type_ids": sorted(
            item.encounter_set_type_id for item in profile.encounter_set_types if item.active
        ),
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
