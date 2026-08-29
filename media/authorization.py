"""Patient-media lineage resolution and mandatory object authorization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from authz import (
    AuthorizationDenied,
    RecordScope,
    ScopeCheck,
    access_context,
    admin_scope,
    assigned_lab_scope,
    hospital_scope,
    project_scope,
    require_any,
    self_scope,
    upload_scope,
)
from models import (
    DiabeticRetinopathyReport,
    DirectImageUpload,
    EncounterFile,
    EncounterFilePDF,
    EncounterSetImage,
    GlaucomaReport,
    GradingTask,
    LabUnit,
    PatientEncounters,
)


class MediaSourceType(StrEnum):
    """Supported patient-media persistence sources normalized by this layer."""

    ENCOUNTER_FILE = "encounter_file"
    DIRECT_IMAGE_UPLOAD = "direct_image_upload"
    ENCOUNTER_SET_IMAGE = "encounter_set_image"
    ENCOUNTER_FILE_PDF = "encounter_file_pdf"
    DR_REPORT = "dr_report"
    GLAUCOMA_REPORT = "glaucoma_report"


IMAGE_SOURCE_TYPES = frozenset({
    MediaSourceType.ENCOUNTER_FILE,
    MediaSourceType.DIRECT_IMAGE_UPLOAD,
    MediaSourceType.ENCOUNTER_SET_IMAGE,
})
DOCUMENT_SOURCE_TYPES = frozenset({
    MediaSourceType.ENCOUNTER_FILE_PDF,
    MediaSourceType.DR_REPORT,
    MediaSourceType.GLAUCOMA_REPORT,
})


@dataclass(frozen=True)
class AuthorizedMediaSource:
    """Authorized, storage-independent identity and scope for one media object."""

    source_type: MediaSourceType
    source_id: int
    uuid: str
    patient_encounter_id: int | None
    project_id: int | None
    hospital_id: int | None
    lab_unit_id: int | None
    disease_id: int | None
    uploader_user_id: int | None = None
    upload_profile_id: int | None = None

    def record_scope(self) -> RecordScope:
        """Return complete media lineage, denying ambiguous or missing facts."""
        if self.lab_unit_id is None or self.hospital_id is None:
            raise MediaResolutionError("Media not found")
        if self.project_id is None:
            return RecordScope.classical(
                lab_unit_id=self.lab_unit_id,
                hospital_id=self.hospital_id,
            )
        return RecordScope.project(
            project_id=self.project_id,
            lab_unit_id=self.lab_unit_id,
            hospital_id=self.hospital_id,
        )


class MediaResolutionError(LookupError):
    """Raised for missing, ambiguous, or lineage-conflicting media."""


class MediaAccessDenied(PermissionError):
    """Raised when a resolved media object is outside the actor's authority."""


def resolve_media_source(
    db: Session,
    *,
    media_uuid: str,
    expected_sources: frozenset[MediaSourceType] | None = None,
) -> AuthorizedMediaSource:
    """Resolve one UUID across all patient-media tables and normalize its lineage."""
    matches: list[AuthorizedMediaSource] = []

    encounter_file = db.execute(
        select(EncounterFile).where(EncounterFile.uuid == media_uuid)
    ).scalar_one_or_none()
    if encounter_file:
        matches.append(_from_encounter_child(db, MediaSourceType.ENCOUNTER_FILE, encounter_file))

    direct_image = db.execute(
        select(DirectImageUpload).where(DirectImageUpload.uuid == media_uuid)
    ).scalar_one_or_none()
    if direct_image:
        matches.append(AuthorizedMediaSource(
            source_type=MediaSourceType.DIRECT_IMAGE_UPLOAD,
            source_id=direct_image.id,
            uuid=direct_image.uuid,
            patient_encounter_id=None,
            project_id=direct_image.project_id,
            hospital_id=direct_image.hospital_id,
            lab_unit_id=direct_image.lab_unit_id,
            disease_id=direct_image.disease_id,
            uploader_user_id=direct_image.uploader_id,
        ))

    set_image = db.execute(
        select(EncounterSetImage).where(EncounterSetImage.uuid == media_uuid)
    ).scalar_one_or_none()
    if set_image:
        matches.append(_from_encounter_child(db, MediaSourceType.ENCOUNTER_SET_IMAGE, set_image))

    encounter_pdf = db.execute(
        select(EncounterFilePDF).where(EncounterFilePDF.uuid == media_uuid)
    ).scalar_one_or_none()
    if encounter_pdf:
        matches.append(_from_encounter_child(db, MediaSourceType.ENCOUNTER_FILE_PDF, encounter_pdf))

    dr_report = db.execute(
        select(DiabeticRetinopathyReport).where(DiabeticRetinopathyReport.uuid == media_uuid)
    ).scalar_one_or_none()
    if dr_report:
        matches.append(_from_encounter_child(db, MediaSourceType.DR_REPORT, dr_report))

    glaucoma_report = db.execute(
        select(GlaucomaReport).where(GlaucomaReport.uuid == media_uuid)
    ).scalar_one_or_none()
    if glaucoma_report:
        matches.append(_from_encounter_child(db, MediaSourceType.GLAUCOMA_REPORT, glaucoma_report))

    if len(matches) != 1:
        raise MediaResolutionError("Media not found")
    resource = matches[0]
    if expected_sources is not None and resource.source_type not in expected_sources:
        raise MediaResolutionError("Media not found")
    return resource


def authorize_media_source(
    db: Session,
    *,
    user,
    media_uuid: str,
    action: str | None = None,
    expected_sources: frozenset[MediaSourceType] | None = None,
) -> AuthorizedMediaSource:
    """Resolve media and apply current role plus exact persisted scope."""
    resource = resolve_media_source(
        db,
        media_uuid=media_uuid,
        expected_sources=expected_sources,
    )
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        raise MediaAccessDenied("Media not found")

    context = access_context(db, user)
    record = resource.record_scope()
    if resource.source_type in DOCUMENT_SOURCE_TYPES:
        checks = [
            admin_scope(context),
            assigned_lab_scope(context, {"fileuploader", "pregarded_uploader"}, record),
            assigned_lab_scope(context, {"verifier"}, record),
            project_scope(context, {"verifier"}, record),
            upload_scope(
                context,
                {"fileuploader", "pregarded_uploader"},
                record,
                upload_profile_id=resource.upload_profile_id,
            ),
        ]
        try:
            require_any(*checks)
        except AuthorizationDenied as exc:
            raise MediaAccessDenied("Media not found") from exc
        return resource

    image_roles = {
        "local_admin", "data_manager", "fileUploader", "ophthalmologist",
        "optometrist", "verifier", "field_optometrist", "field_ophthalmologist",
    }
    result_roles = {
        "local_admin", "data_manager", "analytics_viewer", "discrepancy_reviewer",
        "data_exporter", "dataset_creator", "regrade_adjudicator",
    }
    classical_roles = image_roles if resource.source_type in IMAGE_SOURCE_TYPES else result_roles
    project_roles = {
        "project_pi", "site_pi", "project_admin", "collaborator",
    } | (image_roles if resource.source_type in IMAGE_SOURCE_TYPES else result_roles)

    checks = [
        admin_scope(context),
        assigned_lab_scope(context, classical_roles, record),
        hospital_scope(context, classical_roles, record),
        project_scope(context, project_roles, record),
    ]
    if (
        resource.uploader_user_id == context.user_id
        and context.has_any_global_role(frozenset({"fileuploader", "pregarded_uploader"}))
    ):
        checks.append(self_scope(context, resource.uploader_user_id))
    if resource.source_type in IMAGE_SOURCE_TYPES:
        checks.extend(_task_grading_checks(db, context=context, resource=resource))
    try:
        require_any(*checks)
    except AuthorizationDenied as exc:
        raise MediaAccessDenied("Media not found")
    return resource


def authorize_signed_media_source(
    *, resource: AuthorizedMediaSource, action: str | None = None
) -> None:
    """Require complete lineage after the route validates the signed token."""
    resource.record_scope()


def _from_encounter_child(db: Session, source_type: MediaSourceType, row) -> AuthorizedMediaSource:
    """Resolve inherited encounter lineage and reject conflicting child scope."""
    encounter = db.get(PatientEncounters, row.patient_encounter_id)
    if encounter is None:
        raise MediaResolutionError("Media not found")
    child_project_id = getattr(row, "project_id", None)
    child_lab_unit_id = getattr(row, "lab_unit_id", None)
    child_hospital_id = getattr(row, "hospital_id", None)
    if child_project_id and encounter.project_id and child_project_id != encounter.project_id:
        raise MediaResolutionError("Media not found")
    if child_lab_unit_id and encounter.lab_unit_id and child_lab_unit_id != encounter.lab_unit_id:
        raise MediaResolutionError("Media not found")
    project_id = child_project_id or encounter.project_id
    lab_unit_id = child_lab_unit_id or encounter.lab_unit_id
    derived_hospital_id = db.execute(
        select(LabUnit.hospital_id).where(LabUnit.id == lab_unit_id)
    ).scalar_one_or_none() if lab_unit_id else None
    if child_hospital_id and derived_hospital_id and child_hospital_id != derived_hospital_id:
        raise MediaResolutionError("Media not found")
    return AuthorizedMediaSource(
        source_type=source_type,
        source_id=row.id,
        uuid=row.uuid,
        patient_encounter_id=encounter.id,
        project_id=project_id,
        hospital_id=child_hospital_id or derived_hospital_id,
        lab_unit_id=lab_unit_id,
        disease_id=encounter.disease_id,
        uploader_user_id=None,
        upload_profile_id=encounter.upload_profile_id,
    )


def _task_grading_checks(
    db: Session, *, context, resource: AuthorizedMediaSource
) -> list[ScopeCheck]:
    """Return exact current grading checks for every task on this image."""
    query = select(GradingTask)
    if resource.source_type == MediaSourceType.ENCOUNTER_FILE:
        query = query.where(GradingTask.encounter_file_id == resource.source_id)
    elif resource.source_type == MediaSourceType.DIRECT_IMAGE_UPLOAD:
        query = query.where(GradingTask.direct_image_upload_id == resource.source_id)
    elif resource.source_type == MediaSourceType.ENCOUNTER_SET_IMAGE:
        query = query.where(GradingTask.encounter_set_image_id == resource.source_id)
    else:
        return []
    tasks = db.execute(query).scalars().all()
    from grading_allocation.eligibility import is_user_eligible_for_task

    checks: list[ScopeCheck] = []
    for task in tasks:
        if (
            task.project_id != resource.project_id
            or task.lab_unit_id != resource.lab_unit_id
        ):
            continue
        for slot in ("resident", "resident2", "arbitrator"):
            checks.append(
                ScopeCheck(
                    is_user_eligible_for_task(
                        db,
                        user_id=context.user_id,
                        task=task,
                        role_slot=slot,
                    ),
                    "grading_task_eligibility_required",
                    "exact_grading_task_eligibility",
                )
            )
    return checks
