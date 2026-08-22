"""Preview and repair IITK clinical-image grading task eligibility."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256

from sqlalchemy import and_, or_

from models import (
    EncounterSetGradingPackage,
    EncounterSetImage,
    Grade,
    GradingTask,
    PatientEncounters,
    Project,
)


class IITKTaskEligibilityError(ValueError):
    """Raised when a requested IITK eligibility repair is not safe to apply."""


@dataclass(frozen=True)
class IITKTaskEligibilityPreview:
    project_id: int
    project_code: str
    project_title: str
    images_to_update: int
    encounters_affected: int
    encounter_status_counts: dict[str, int]
    packages: int
    tasks: int
    image_tasks: int
    grades: int
    confirmation_token: str

    def to_dict(self) -> dict:
        return asdict(self)


def preview_iitk_task_eligibility(db, *, project_id: int, lock: bool = False) -> IITKTaskEligibilityPreview:
    project = db.get(Project, project_id)
    if project is None:
        raise IITKTaskEligibilityError("Project was not found.")

    query = (
        db.query(EncounterSetImage, PatientEncounters)
        .join(PatientEncounters, PatientEncounters.id == EncounterSetImage.patient_encounter_id)
        .filter(
            EncounterSetImage.asset_kind == "clinical_image",
            EncounterSetImage.creates_task.is_(False),
            or_(
                EncounterSetImage.project_id == project_id,
                and_(
                    EncounterSetImage.project_id.is_(None),
                    PatientEncounters.project_id == project_id,
                ),
            ),
        )
        .order_by(EncounterSetImage.id)
    )
    if lock:
        query = query.with_for_update()
    rows = [
        (image, encounter)
        for image, encounter in query.all()
        if _is_iitk_source(image, encounter)
    ]
    encounter_by_id = {encounter.id: encounter for _, encounter in rows}
    encounter_ids = tuple(sorted(encounter_by_id))
    image_ids = tuple(image.id for image, _ in rows)

    package_ids: tuple[int, ...] = ()
    task_rows: list[tuple[int, str]] = []
    grade_count = 0
    if encounter_ids:
        package_ids = tuple(
            item[0]
            for item in db.query(EncounterSetGradingPackage.id)
            .filter(EncounterSetGradingPackage.patient_encounter_id.in_(encounter_ids))
            .all()
        )
        if package_ids:
            task_rows = db.query(GradingTask.id, GradingTask.grading_target_level).filter(
                GradingTask.encounter_set_package_id.in_(package_ids)
            ).all()
            task_ids = tuple(item[0] for item in task_rows)
            if task_ids:
                grade_count = db.query(Grade.id).filter(Grade.task_id.in_(task_ids)).count()

    status_counts = Counter(
        str(encounter.encounter_verified_status or "unknown")
        for encounter in encounter_by_id.values()
    )
    fingerprint = sha256(
        f"project={project_id};images={','.join(str(value) for value in image_ids)}".encode()
    ).hexdigest()[:12].upper()
    return IITKTaskEligibilityPreview(
        project_id=project.id,
        project_code=project.code,
        project_title=project.title,
        images_to_update=len(image_ids),
        encounters_affected=len(encounter_ids),
        encounter_status_counts=dict(sorted(status_counts.items())),
        packages=len(package_ids),
        tasks=len(task_rows),
        image_tasks=sum(1 for _, target_level in task_rows if target_level == "image"),
        grades=grade_count,
        confirmation_token=f"IITK-TASKS-{project_id}-{fingerprint}",
    )


def apply_iitk_task_eligibility(
    db,
    *,
    project_id: int,
    confirmation_token: str,
) -> IITKTaskEligibilityPreview:
    preview = preview_iitk_task_eligibility(db, project_id=project_id, lock=True)
    if not confirmation_token or confirmation_token != preview.confirmation_token:
        raise IITKTaskEligibilityError(
            "The confirmation token does not match the current IITK image population. Run preview again."
        )
    if preview.images_to_update:
        rows = (
            db.query(EncounterSetImage)
            .filter(EncounterSetImage.id.in_(_candidate_image_ids(db, project_id=project_id)))
            .all()
        )
        for image in rows:
            image.creates_task = True
        db.flush()
    return preview


def _candidate_image_ids(db, *, project_id: int) -> tuple[int, ...]:
    query = (
        db.query(EncounterSetImage, PatientEncounters)
        .join(PatientEncounters, PatientEncounters.id == EncounterSetImage.patient_encounter_id)
        .filter(
            EncounterSetImage.asset_kind == "clinical_image",
            EncounterSetImage.creates_task.is_(False),
            or_(
                EncounterSetImage.project_id == project_id,
                and_(EncounterSetImage.project_id.is_(None), PatientEncounters.project_id == project_id),
            ),
        )
        .order_by(EncounterSetImage.id)
    )
    return tuple(
        image.id
        for image, encounter in query.all()
        if _is_iitk_source(image, encounter)
    )


def _is_iitk_source(image: EncounterSetImage, encounter: PatientEncounters) -> bool:
    image_metadata = image.metadata_json if isinstance(image.metadata_json, dict) else {}
    encounter_metadata = encounter.metadata_json if isinstance(encounter.metadata_json, dict) else {}
    upload_metadata = (
        encounter_metadata.get("upload")
        if isinstance(encounter_metadata.get("upload"), dict)
        else {}
    )
    return (image_metadata.get("source_kind") or upload_metadata.get("source_kind")) == "iitk_api"
