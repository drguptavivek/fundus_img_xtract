"""Exact upload targets with server-validated scope and profile identity."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from authz_v2.core.resources import DisclosureClass, ResourceContextDTO
from authz_v2.domain.models import AuthorizationResourceScope
from authz_v2.resources.references import is_positive_int
from authz_v2.resources.registry import ResourceTarget
from authz_v2.resources.scoping import resolve_scope
from project_configuration.models import ProjectLabUnit
from upload_profiles.models import ProjectUploadProfile, UploadProfile


@dataclass(frozen=True)
class UploadTargetRef:
    """Exact target/profile identity; both values are reloaded."""

    target_id: int
    upload_profile_id: int


@dataclass(frozen=True)
class ResolvedUploadTarget:
    target: object
    profile: UploadProfile
    project_profile_id: int | None
    target_active: bool


def _resource_id(reference: UploadTargetRef) -> str:
    return f"{reference.target_id}:{reference.upload_profile_id}"


def resolve_project_upload_target(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, UploadTargetRef) or not all(
        is_positive_int(value)
        for value in (reference.target_id, reference.upload_profile_id)
    ):
        return None
    project_lab = db.get(ProjectLabUnit, reference.target_id)
    profile = db.get(UploadProfile, reference.upload_profile_id)
    if project_lab is None or profile is None:
        return None
    project_profile = db.execute(
        select(ProjectUploadProfile).where(
            ProjectUploadProfile.project_id == project_lab.project_id,
            ProjectUploadProfile.upload_profile_id == profile.id,
        )
    ).scalar_one_or_none()
    if project_profile is None:
        return None
    scope = resolve_scope(
        db,
        project_id=project_lab.project_id,
        lab_unit_id=project_lab.lab_unit_id,
    )
    if scope is None:
        return None
    target_active = bool(
        project_lab.active and project_profile.active and profile.active
    )
    value = ResolvedUploadTarget(
        project_lab,
        profile,
        project_profile.id,
        target_active,
    )
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "project_upload_target",
            _resource_id(reference),
            scope,
            disclosure_class=DisclosureClass.IDENTIFIER_IN_PLACE,
            state={
                "target_active": target_active,
                "domain_valid": target_active,
            },
        ),
    )


def resolve_classical_upload_target(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, UploadTargetRef) or not all(
        is_positive_int(value)
        for value in (reference.target_id, reference.upload_profile_id)
    ):
        return None
    binding = db.get(AuthorizationResourceScope, reference.target_id)
    profile = db.get(UploadProfile, reference.upload_profile_id)
    if (
        binding is None
        or profile is None
        or binding.resource_type != "upload_target"
        or not binding.active
        or binding.project_id is not None
    ):
        return None
    scope = resolve_scope(
        db, lab_unit_id=binding.lab_unit_id, hospital_id=binding.hospital_id
    )
    if scope is None:
        return None
    target_active = bool(binding.domain_valid and profile.active)
    value = ResolvedUploadTarget(
        binding,
        profile,
        None,
        target_active,
    )
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "upload_target",
            _resource_id(reference),
            scope,
            disclosure_class=DisclosureClass.IDENTIFIER_IN_PLACE,
            state={
                "target_active": target_active,
                "domain_valid": target_active,
            },
        ),
    )
