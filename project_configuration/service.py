"""Project Lab Unit boundary configuration and validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from models import LabUnit, Project

from .models import ProjectLabUnit


class ProjectLabConfigurationError(ValueError):
    pass


class ProjectLabConfigurationDenied(PermissionError):
    pass


MAX_VERIFICATION_TAGS = 30
MAX_VERIFICATION_TAG_LENGTH = 80


@dataclass(frozen=True)
class ProjectVerificationTagsDTO:
    project_id: int
    tags: tuple[str, ...]


def _normalize_verification_tags(values: Iterable[str]) -> tuple[str, ...]:
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ProjectLabConfigurationError("Each verification tag must be a string.")
        tag = " ".join(value.split()).strip()
        if not tag:
            continue
        if ";" in tag:
            raise ProjectLabConfigurationError("Verification tags cannot contain semicolons.")
        if len(tag) > MAX_VERIFICATION_TAG_LENGTH:
            raise ProjectLabConfigurationError(
                f"Verification tags cannot exceed {MAX_VERIFICATION_TAG_LENGTH} characters."
            )
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            tags.append(tag)
    if len(tags) > MAX_VERIFICATION_TAGS:
        raise ProjectLabConfigurationError(
            f"A project can have at most {MAX_VERIFICATION_TAGS} verification tags."
        )
    return tuple(tags)


def get_project_verification_tags(db: Session, *, project_id: int) -> ProjectVerificationTagsDTO:
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectLabConfigurationError("Project not found.")
    return ProjectVerificationTagsDTO(
        project_id=project.id,
        tags=tuple(project.verification_tags_json or []),
    )


def replace_project_verification_tags(
    db: Session,
    *,
    actor: Any,
    project_id: int,
    tags: Iterable[str],
) -> ProjectVerificationTagsDTO:
    """Replace verifier quick-add tags; only System Admin may mutate them."""
    if not actor.has_role("admin"):
        raise ProjectLabConfigurationDenied(
            "Only a System Admin can configure project verification tags."
        )
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectLabConfigurationError("Project not found.")
    normalized = _normalize_verification_tags(tags)
    project.verification_tags_json = list(normalized)
    db.flush()
    return ProjectVerificationTagsDTO(project_id=project.id, tags=normalized)


@dataclass(frozen=True)
class ProjectLabUnitDTO:
    id: int
    project_id: int
    lab_unit_id: int
    lab_unit_name: str
    hospital_id: int
    hospital_name: str
    active: bool
    sites_can_export_grades: bool
    sites_can_create_datasets: bool
    sites_can_share_datasets: bool


SITE_FEATURE_FIELDS = frozenset(
    {
        "sites_can_export_grades",
        "sites_can_create_datasets",
        "sites_can_share_datasets",
    }
)


def configured_project_lab_unit_ids(db: Session, *, project_id: int) -> frozenset[int]:
    """Return the active Lab Units that bound all access inside a project."""
    return frozenset(db.execute(
        select(ProjectLabUnit.lab_unit_id).where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.active.is_(True),
        )
    ).scalars())


def list_project_lab_units(db: Session, *, project_id: int) -> tuple[ProjectLabUnitDTO, ...]:
    rows = db.execute(
        select(ProjectLabUnit)
        .where(ProjectLabUnit.project_id == project_id)
        .options(selectinload(ProjectLabUnit.lab_unit).selectinload(LabUnit.hospital))
        .order_by(ProjectLabUnit.active.desc(), ProjectLabUnit.lab_unit_id)
    ).scalars().all()
    return tuple(
        ProjectLabUnitDTO(
            id=row.id,
            project_id=row.project_id,
            lab_unit_id=row.lab_unit_id,
            lab_unit_name=row.lab_unit.name,
            hospital_id=row.lab_unit.hospital_id,
            hospital_name=row.lab_unit.hospital.name,
            active=row.active,
            sites_can_export_grades=row.sites_can_export_grades,
            sites_can_create_datasets=row.sites_can_create_datasets,
            sites_can_share_datasets=row.sites_can_share_datasets,
        )
        for row in rows
    )


def replace_project_lab_units(
    db: Session,
    *,
    actor: Any,
    project_id: int,
    lab_unit_ids: Iterable[int],
    site_settings: dict[int, dict[str, bool]] | None = None,
) -> tuple[ProjectLabUnitDTO, ...]:
    """Replace the project boundary; only System Admin may mutate it."""
    if not actor.has_role("admin"):
        raise ProjectLabConfigurationDenied("Only a System Admin can configure project Lab Units.")
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectLabConfigurationError("Project not found.")
    selected_ids = {int(value) for value in lab_unit_ids if int(value) > 0}
    existing_lab_ids = set(db.execute(
        select(LabUnit.id).where(LabUnit.id.in_(selected_ids or {-1}))
    ).scalars())
    if existing_lab_ids != selected_ids:
        raise ProjectLabConfigurationError("One or more selected Lab Units do not exist.")
    normalized_settings = site_settings or {}
    if set(normalized_settings) - selected_ids:
        raise ProjectLabConfigurationError("Site settings require an active selected Lab Unit.")
    for settings in normalized_settings.values():
        if set(settings) - SITE_FEATURE_FIELDS or any(
            type(value) is not bool for value in settings.values()
        ):
            raise ProjectLabConfigurationError("Project site settings must be explicit booleans.")

    existing = {
        row.lab_unit_id: row
        for row in db.execute(
            select(ProjectLabUnit).where(ProjectLabUnit.project_id == project_id)
        ).scalars()
    }
    for lab_unit_id, row in existing.items():
        row.active = lab_unit_id in selected_ids
        for field_name, value in normalized_settings.get(lab_unit_id, {}).items():
            setattr(row, field_name, value)
    for lab_unit_id in selected_ids - set(existing):
        row = ProjectLabUnit(project_id=project_id, lab_unit_id=lab_unit_id, active=True)
        for field_name, value in normalized_settings.get(lab_unit_id, {}).items():
            setattr(row, field_name, value)
        db.add(row)

    # Remove latent access outside the new boundary. Rows are retained for audit
    # history and can be deliberately re-created if the Lab Unit is added later.
    from data_authorization.models import LAB_UNIT_SCOPE, ProjectRoleGrant
    from grading_allocation.models import ProjectGraderAllocation
    from iitk_api_integration.models import IITKApiProjectConfig
    from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding
    from upload_profiles.models import ProjectUploadProfile, ProjectUploadProfileAssignment

    db.execute(
        update(ProjectRoleGrant)
        .where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.active.is_(True),
            ProjectRoleGrant.scope_type == LAB_UNIT_SCOPE,
            ProjectRoleGrant.lab_unit_id.not_in(selected_ids or {-1}),
        )
        .values(active=False)
    )
    db.execute(
        update(ProjectUploadProfileAssignment)
        .where(
            ProjectUploadProfileAssignment.project_upload_profile_id.in_(
                select(ProjectUploadProfile.id).where(ProjectUploadProfile.project_id == project_id)
            ),
            ProjectUploadProfileAssignment.active.is_(True),
            ProjectUploadProfileAssignment.lab_unit_id.not_in(selected_ids or {-1}),
        )
        .values(active=False)
    )
    for model in (ProjectGraderAllocation, IITKApiProjectConfig):
        db.execute(
            update(model)
            .where(
                model.project_id == project_id,
                model.active.is_(True),
                model.lab_unit_id.not_in(selected_ids or {-1}),
            )
            .values(active=False)
        )
    db.execute(
        update(ProjectUploadProfileRemidioApiBinding)
        .where(
            ProjectUploadProfileRemidioApiBinding.project_upload_profile_id.in_(
                select(ProjectUploadProfile.id).where(ProjectUploadProfile.project_id == project_id)
            ),
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.lab_unit_id.not_in(selected_ids or {-1}),
        )
        .values(active=False)
    )
    db.flush()
    return list_project_lab_units(db, project_id=project_id)


def validate_project_lab_unit(db: Session, *, project_id: int, lab_unit_id: int) -> None:
    if lab_unit_id not in configured_project_lab_unit_ids(db, project_id=project_id):
        raise ProjectLabConfigurationError("Selected Lab Unit is not configured for this project.")


def project_site_feature_allows(
    db: Session,
    *,
    project_id: int | None,
    lab_unit_id: int | None,
    authority_scope_type: str | None,
    feature: str,
) -> bool:
    """Check one persisted site feature flag; incomplete facts deny."""
    if feature not in SITE_FEATURE_FIELDS or not project_id:
        return False
    if authority_scope_type == "project":
        return True
    if authority_scope_type != "lab_unit" or not lab_unit_id:
        return False
    return bool(
        db.execute(
            select(getattr(ProjectLabUnit, feature)).where(
                ProjectLabUnit.project_id == project_id,
                ProjectLabUnit.lab_unit_id == lab_unit_id,
                ProjectLabUnit.active.is_(True),
            )
        ).scalar_one_or_none()
    )
