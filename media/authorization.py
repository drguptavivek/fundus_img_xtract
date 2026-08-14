"""Patient-media lineage resolution and mandatory object authorization.

This is the media enforcement layer.  It resolves a UUID without trusting
route context, derives project/hospital/lab lineage, gathers relationships from
the existing grant modules, and delegates the decision to :mod:`authz`.  It
does not select storage paths or return media bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from authz import (
    AuthzActor,
    GrantSource,
    RelationshipGrant,
    ResourceRef,
    actor_from_user,
    admin_global_grant,
    authorize,
    general_scope_grants,
)
from authz.cache import get_cached_decision, set_cached_decision
from authz.telemetry import record_authorization_decision
from data_authorization.service import project_role_names_for_scope
from encounter_sets.permissions import (
    legacy_project_capabilities_for_scope,
    user_is_legacy_project_collaborator,
)
from grading_allocation.eligibility import is_user_eligible_for_task
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

    def as_resource_ref(self) -> ResourceRef:
        """Convert this resolved source into the central engine resource contract."""
        return ResourceRef(
            type=self.source_type.value,
            id=self.uuid,
            attributes={
                "source_id": self.source_id,
                "patient_encounter_id": self.patient_encounter_id,
                "project_id": self.project_id,
                "hospital_id": self.hospital_id,
                "lab_unit_id": self.lab_unit_id,
                "disease_id": self.disease_id,
                "uploader_user_id": self.uploader_user_id,
            },
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
    action: str,
    expected_sources: frozenset[MediaSourceType] | None = None,
) -> AuthorizedMediaSource:
    """Resolve and authorize one media object through the central authz engine."""
    try:
        resource = resolve_media_source(
            db,
            media_uuid=media_uuid,
            expected_sources=expected_sources,
        )
    except MediaResolutionError:
        record_authorization_decision(
            action=action,
            allowed=False,
            actor_id=getattr(user, "id", None),
        )
        raise
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        record_authorization_decision(
            action=action,
            allowed=False,
            actor_id=getattr(user, "id", None),
        )
        raise MediaAccessDenied("Media not found")

    resource_ref = resource.as_resource_ref()
    cached = get_cached_decision(user_id=user.id, action=action, resource=resource_ref)
    if cached is not None:
        record_authorization_decision(
            action=action,
            allowed=cached.allowed,
            actor_id=user.id,
            grant_source=cached.grant_source,
            cache_hit=True,
        )
        if not cached.allowed:
            raise MediaAccessDenied("Media not found")
        return resource

    actor = actor_from_user(user)
    grants = _relationship_grants(db, user=user, actor=actor, resource=resource)
    decision = authorize(actor, action, resource_ref, grants=grants)
    set_cached_decision(
        user_id=user.id,
        action=action,
        resource=resource_ref,
        decision=decision,
    )
    record_authorization_decision(
        action=action,
        allowed=decision.allowed,
        actor_id=user.id,
        grant_source=decision.grant_source,
    )
    if not decision.allowed:
        raise MediaAccessDenied("Media not found")
    return resource


def authorize_signed_media_source(
    *, resource: AuthorizedMediaSource, action: str
) -> None:
    """Apply central policy to a separately validated signed-media credential."""
    actor = AuthzActor(id=0)
    decision = authorize(
        actor,
        action,
        resource.as_resource_ref(),
        grants=[RelationshipGrant(
            source=GrantSource.SIGNED_MEDIA_TOKEN,
            resource_id=resource.uuid,
        )],
    )
    record_authorization_decision(
        action=action,
        allowed=decision.allowed,
        actor_id=None,
        grant_source=decision.grant_source,
    )
    if not decision.allowed:
        raise MediaAccessDenied("Media not found")


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
    )


def _relationship_grants(
    db: Session, *, user, actor: AuthzActor, resource: AuthorizedMediaSource
) -> list[RelationshipGrant]:
    """Gather persisted scope, compatibility, ownership, and task relationships."""
    grants: list[RelationshipGrant] = []
    if resource.project_id is None:
        grants.extend(general_scope_grants(user))
    else:
        admin_grant = admin_global_grant(actor)
        if admin_grant:
            grants.append(admin_grant)
        role_names = project_role_names_for_scope(
            db,
            user_id=user.id,
            project_id=resource.project_id,
            hospital_id=resource.hospital_id,
            lab_unit_id=resource.lab_unit_id,
        )
        if role_names:
            grants.append(RelationshipGrant(
                source=GrantSource.PROJECT_ROLE,
                attributes={
                    "project_id": resource.project_id,
                    "hospital_id": resource.hospital_id,
                    "lab_unit_id": resource.lab_unit_id,
                    "role_names": role_names,
                },
            ))
        if resource.lab_unit_id:
            capabilities = legacy_project_capabilities_for_scope(
                db,
                user_id=user.id,
                project_id=resource.project_id,
                lab_unit_id=resource.lab_unit_id,
            )
            if capabilities:
                grants.append(RelationshipGrant(
                    source=GrantSource.LEGACY_PROJECT_CAPABILITY,
                    attributes={
                        "project_id": resource.project_id,
                        "hospital_id": resource.hospital_id,
                        "lab_unit_id": resource.lab_unit_id,
                        "capabilities": capabilities,
                    },
                ))
        if user_is_legacy_project_collaborator(
            db,
            user_id=user.id,
            project_id=resource.project_id,
        ):
            grants.append(RelationshipGrant(
                source=GrantSource.PROJECT_COLLABORATOR,
                attributes={
                    "project_id": resource.project_id,
                    "hospital_id": resource.hospital_id,
                    "lab_unit_id": resource.lab_unit_id,
                },
            ))
    if resource.uploader_user_id == user.id:
        grants.append(RelationshipGrant(
            source=GrantSource.MEDIA_UPLOADER,
            resource_id=resource.uuid,
        ))
    if resource.source_type in IMAGE_SOURCE_TYPES and _has_task_eligibility(db, user.id, resource):
        grants.append(RelationshipGrant(
            source=GrantSource.TASK_ELIGIBILITY,
            resource_id=resource.uuid,
        ))
    return grants


def _has_task_eligibility(db: Session, user_id: int, resource: AuthorizedMediaSource) -> bool:
    """Return whether any task for this image is eligible in a grading role slot."""
    query = select(GradingTask)
    if resource.source_type == MediaSourceType.ENCOUNTER_FILE:
        query = query.where(GradingTask.encounter_file_id == resource.source_id)
    elif resource.source_type == MediaSourceType.DIRECT_IMAGE_UPLOAD:
        query = query.where(GradingTask.direct_image_upload_id == resource.source_id)
    elif resource.source_type == MediaSourceType.ENCOUNTER_SET_IMAGE:
        query = query.where(GradingTask.encounter_set_image_id == resource.source_id)
    else:
        return False
    tasks = db.execute(query).scalars().all()
    return any(
        is_user_eligible_for_task(db, user_id=user_id, task=task, role_slot=role_slot)
        for task in tasks
        for role_slot in ("resident", "resident2", "arbitrator")
    )
