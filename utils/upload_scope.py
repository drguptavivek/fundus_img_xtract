"""Project-scoped upload eligibility and validation interfaces.

This module owns upload intake scoping for direct image, pregraded, Remedio ZIP,
and encounter-set uploads. Public helpers return plain dataclasses or built-in
containers, never SQLAlchemy ORM instances, so callers can safely pass results to
templates, sidecar metadata, Celery tasks, or post-commit enqueue code without
lazy-loading or detached-instance failures.

Upload permission is granted only by active ``UploadMapping`` rows and explicit
lab-unit membership. Project investigator membership is governance metadata and
does not grant upload permission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession, selectinload

from db_transaction_manager import get_db_session
from models import (
    Area,
    Camera,
    Disease,
    LabUnit,
    Project,
    UploadMapping,
    UploadMappingArea,
    UploadMappingCamera,
    User,
)


class UploadScopeError(ValueError):
    """Safe upload-scope validation error for user-facing route handling."""

    def __init__(self, message: str, *, code: str = "invalid_upload_scope") -> None:
        """Create an upload scope error.

        Args:
            message: Safe user-facing message suitable for flash/API response.
            code: Machine-readable reason for tests and API clients.
        """
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class UploadScopeSelection:
    """Normalized direct/pregraded upload selection.

    All fields are scalar request values. ``is_mydriatic`` is the user's selected
    mydriatic state and must be checked against the mapping's allowed states.
    """

    project_id: int
    lab_unit_id: int
    disease_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool


@dataclass(frozen=True)
class UploadScopeMapping:
    """Route-facing upload mapping DTO with no ORM instances.

    IDs are scalar database identifiers. Name fields are display labels resolved
    while the DB session is active. Allowed camera/area IDs are sets for cheap
    validation by callers that need secondary checks.
    """

    mapping_id: int
    user_id: int
    project_id: int
    project_title: str
    project_code: str
    lab_unit_id: int
    lab_unit_name: str
    hospital_id: int
    disease_id: int
    disease_name: str
    default_disease_id: int | None
    default_disease_name: str | None
    allowed_camera_ids: frozenset[int]
    allowed_area_ids: frozenset[int]
    allow_mydriatic: bool
    allow_non_mydriatic: bool
    default_is_mydriatic: bool


@dataclass(frozen=True)
class UploadOptions:
    """UI-ready upload option payload for templates and JSON responses."""

    projects: list[dict[str, Any]]
    lab_units: list[dict[str, Any]]
    diseases: list[dict[str, Any]]
    cameras: list[dict[str, Any]]
    areas: list[dict[str, Any]]
    mappings: list[dict[str, Any]]


def _active_mapping_query(db: OrmSession, user_id: int):
    """Return the base eager-loaded active mapping query for a user."""
    return (
        db.query(UploadMapping)
        .join(Project, UploadMapping.project_id == Project.id)
        .options(
            selectinload(UploadMapping.project),
            selectinload(UploadMapping.lab_unit),
            selectinload(UploadMapping.disease),
            selectinload(UploadMapping.default_disease),
            selectinload(UploadMapping.cameras).selectinload(UploadMappingCamera.camera),
            selectinload(UploadMapping.areas).selectinload(UploadMappingArea.area),
        )
        .filter(
            UploadMapping.user_id == user_id,
            UploadMapping.active.is_(True),
            Project.active.is_(True),
        )
    )


def _explicit_lab_unit_ids(db: OrmSession, user_id: int) -> set[int]:
    """Return explicitly assigned lab units without role/admin expansion."""
    user = (
        db.query(User)
        .options(selectinload(User.lab_units))
        .filter(User.id == user_id)
        .one_or_none()
    )
    if not user or not user.lab_units:
        return set()
    return {lab_unit.id for lab_unit in user.lab_units}


def _mapping_to_dto(mapping: UploadMapping) -> UploadScopeMapping:
    """Serialize an ``UploadMapping`` ORM row to a detached-safe DTO."""
    project = mapping.project
    lab_unit = mapping.lab_unit
    disease = mapping.disease
    default_disease = mapping.default_disease
    return UploadScopeMapping(
        mapping_id=mapping.id,
        user_id=mapping.user_id,
        project_id=mapping.project_id,
        project_title=project.title,
        project_code=project.code,
        lab_unit_id=mapping.lab_unit_id,
        lab_unit_name=lab_unit.name,
        hospital_id=lab_unit.hospital_id,
        disease_id=mapping.disease_id,
        disease_name=disease.name,
        default_disease_id=mapping.default_disease_id,
        default_disease_name=default_disease.name if default_disease else None,
        allowed_camera_ids=frozenset(row.camera_id for row in mapping.cameras),
        allowed_area_ids=frozenset(row.area_id for row in mapping.areas),
        allow_mydriatic=bool(mapping.allow_mydriatic),
        allow_non_mydriatic=bool(mapping.allow_non_mydriatic),
        default_is_mydriatic=bool(mapping.default_is_mydriatic),
    )


def _require_explicit_lab_scope(db: OrmSession, user_id: int, lab_unit_id: int) -> None:
    """Raise when a user is not explicitly assigned to a lab unit."""
    if lab_unit_id not in _explicit_lab_unit_ids(db, user_id):
        raise UploadScopeError(
            "You don't have upload access to the selected lab unit.",
            code="lab_unit_not_allowed",
        )


def _validate_mydriatic(mapping: UploadScopeMapping, is_mydriatic: bool) -> None:
    """Validate the selected mydriatic state against mapping allowances."""
    if is_mydriatic and not mapping.allow_mydriatic:
        raise UploadScopeError("Mydriatic uploads are not allowed for this mapping.", code="mydriatic_not_allowed")
    if not is_mydriatic and not mapping.allow_non_mydriatic:
        raise UploadScopeError("Non-mydriatic uploads are not allowed for this mapping.", code="non_mydriatic_not_allowed")


def _select_default_mapping(mappings: list[UploadScopeMapping]) -> UploadScopeMapping:
    """Select a single mapping with a default disease, rejecting ambiguous defaults."""
    with_defaults = [mapping for mapping in mappings if mapping.default_disease_id is not None]
    if not with_defaults:
        raise UploadScopeError("No default upload disease is configured for this project and lab unit.", code="default_disease_missing")
    default_ids = {mapping.default_disease_id for mapping in with_defaults}
    if len(default_ids) > 1:
        raise UploadScopeError("Multiple default upload diseases are configured for this project and lab unit.", code="default_disease_ambiguous")
    return with_defaults[0]


def get_user_uploadVerify_eligibility(user_id: int) -> Dict[str, Any]:
    """Return legacy hospital/lab-unit upload eligibility for a user.

    This compatibility helper returns plain dictionaries and preserves the
    historical admin behavior for callers that still rely on it.
    """
    with get_db_session() as db:
        user = (
            db.query(User)
            .options(
                selectinload(User.lab_units).selectinload(LabUnit.hospital),
                selectinload(User.roles),
            )
            .filter(User.id == user_id)
            .one_or_none()
        )
        if user is None:
            return {}

        is_admin = any(role.name == "admin" for role in (user.roles or []))
        lab_units_iterable = (
            db.query(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.id).all()
            if is_admin
            else list(user.lab_units or [])
        )

        hospital_map: dict[int, dict[str, Any]] = {}
        for lab_unit in lab_units_iterable:
            hospital = lab_unit.hospital
            if hospital is None:
                continue
            entry = hospital_map.setdefault(
                hospital.id,
                {"hospital_id": hospital.id, "hospital_name": hospital.name, "lab_units": []},
            )
            entry["lab_units"].append({"lab_unit_id": lab_unit.id, "lab_unit_name": lab_unit.name})

        for entry in hospital_map.values():
            entry["lab_units"].sort(key=lambda item: item["lab_unit_id"])

        return {
            "user_id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "hospitals": sorted(hospital_map.values(), key=lambda item: item["hospital_id"]),
        }


def get_user_lab_unit_ids(user_id: int) -> Set[int]:
    """Return lab-unit IDs a user may access, preserving legacy admin expansion."""
    with get_db_session() as db:
        user = (
            db.query(User)
            .options(selectinload(User.lab_units), selectinload(User.roles))
            .filter(User.id == user_id)
            .one_or_none()
        )
        if not user:
            return set()
        if any(role.name == "admin" for role in (user.roles or [])):
            return {row[0] for row in db.query(LabUnit.id).all()}
        return {lab_unit.id for lab_unit in (user.lab_units or [])}


def get_user_lab_unit_ids_no_admin_override(user_id: int) -> Set[int]:
    """Return explicitly assigned lab-unit IDs with no role/admin expansion."""
    with get_db_session() as db:
        return _explicit_lab_unit_ids(db, user_id)


def get_scoped_mapping_admin_lab_unit_ids(user_id: int) -> set[int]:
    """Return lab units a manager may administer for upload mappings.

    This deliberately has no admin override. Admins, local admins, and data
    managers manage only their explicitly assigned lab units.
    """
    return set(get_user_lab_unit_ids_no_admin_override(user_id))


def get_user_upload_mappings(db: OrmSession, user_id: int) -> list[UploadScopeMapping]:
    """Return active project-scoped upload mappings as detached-safe DTOs."""
    explicit_lab_units = _explicit_lab_unit_ids(db, user_id)
    if not explicit_lab_units:
        return []
    mappings = (
        _active_mapping_query(db, user_id)
        .filter(UploadMapping.lab_unit_id.in_(explicit_lab_units))
        .order_by(UploadMapping.project_id, UploadMapping.lab_unit_id, UploadMapping.disease_id)
        .all()
    )
    return [_mapping_to_dto(mapping) for mapping in mappings]


def get_user_upload_options(db: OrmSession, user_id: int) -> UploadOptions:
    """Return UI-ready upload options for the user's active mappings."""
    mappings = get_user_upload_mappings(db, user_id)
    project_map: dict[int, dict[str, Any]] = {}
    lab_map: dict[int, dict[str, Any]] = {}
    disease_map: dict[int, dict[str, Any]] = {}
    camera_ids: set[int] = set()
    area_ids: set[int] = set()

    for mapping in mappings:
        project_map[mapping.project_id] = {
            "id": mapping.project_id,
            "title": mapping.project_title,
            "code": mapping.project_code,
        }
        lab_map[mapping.lab_unit_id] = {
            "id": mapping.lab_unit_id,
            "name": mapping.lab_unit_name,
            "hospital_id": mapping.hospital_id,
        }
        disease_map[mapping.disease_id] = {"id": mapping.disease_id, "name": mapping.disease_name}
        camera_ids.update(mapping.allowed_camera_ids)
        area_ids.update(mapping.allowed_area_ids)

    cameras = [
        {"id": camera.id, "name": camera.name}
        for camera in db.execute(select(Camera).where(Camera.id.in_(camera_ids or {-1})).order_by(Camera.name)).scalars().all()
    ]
    areas = [
        {"id": area.id, "name": area.name}
        for area in db.execute(select(Area).where(Area.id.in_(area_ids or {-1})).order_by(Area.name)).scalars().all()
    ]

    return UploadOptions(
        projects=sorted(project_map.values(), key=lambda item: (item["title"], item["id"])),
        lab_units=sorted(lab_map.values(), key=lambda item: (item["hospital_id"], item["name"], item["id"])),
        diseases=sorted(disease_map.values(), key=lambda item: (item["name"], item["id"])),
        cameras=cameras,
        areas=areas,
        mappings=[
            {
                "mapping_id": mapping.mapping_id,
                "project_id": mapping.project_id,
                "lab_unit_id": mapping.lab_unit_id,
                "disease_id": mapping.disease_id,
                "default_disease_id": mapping.default_disease_id,
                "camera_ids": sorted(mapping.allowed_camera_ids),
                "area_ids": sorted(mapping.allowed_area_ids),
                "allow_mydriatic": mapping.allow_mydriatic,
                "allow_non_mydriatic": mapping.allow_non_mydriatic,
                "default_is_mydriatic": mapping.default_is_mydriatic,
            }
            for mapping in mappings
        ],
    )


def validate_direct_upload_scope(db: OrmSession, user_id: int, selection: UploadScopeSelection) -> UploadScopeMapping:
    """Validate a direct image upload selection and return the matching mapping."""
    _require_explicit_lab_scope(db, user_id, selection.lab_unit_id)
    mappings = [
        mapping
        for mapping in get_user_upload_mappings(db, user_id)
        if mapping.project_id == selection.project_id
        and mapping.lab_unit_id == selection.lab_unit_id
        and mapping.disease_id == selection.disease_id
        and selection.camera_id in mapping.allowed_camera_ids
        and selection.area_id in mapping.allowed_area_ids
    ]
    if not mappings:
        raise UploadScopeError("Selected upload project, disease, camera, or site is not allowed.", code="mapping_not_found")
    mapping = mappings[0]
    _validate_mydriatic(mapping, selection.is_mydriatic)
    return mapping


def validate_pregraded_upload_scope(db: OrmSession, user_id: int, selection: UploadScopeSelection) -> UploadScopeMapping:
    """Validate a pregraded upload selection and return the matching mapping."""
    return validate_direct_upload_scope(db, user_id, selection)


def validate_remedio_upload_scope(
    db: OrmSession,
    user_id: int,
    project_id: int,
    lab_unit_id: int,
    camera_id: int,
) -> UploadScopeMapping:
    """Validate Remedio ZIP upload scope and return the default-disease mapping."""
    _require_explicit_lab_scope(db, user_id, lab_unit_id)
    candidates = [
        mapping
        for mapping in get_user_upload_mappings(db, user_id)
        if mapping.project_id == project_id
        and mapping.lab_unit_id == lab_unit_id
        and camera_id in mapping.allowed_camera_ids
    ]
    if not candidates:
        raise UploadScopeError("Selected project, lab unit, or camera is not allowed for ZIP upload.", code="mapping_not_found")
    return _select_default_mapping(candidates)


def validate_encounter_set_upload_scope(
    db: OrmSession,
    user_id: int,
    project_id: int,
    lab_unit_id: int,
    disease_id: int | None = None,
) -> UploadScopeMapping:
    """Validate encounter-set upload scope and return the target disease mapping."""
    _require_explicit_lab_scope(db, user_id, lab_unit_id)
    candidates = [
        mapping
        for mapping in get_user_upload_mappings(db, user_id)
        if mapping.project_id == project_id and mapping.lab_unit_id == lab_unit_id
    ]
    if disease_id is not None:
        candidates = [mapping for mapping in candidates if mapping.disease_id == disease_id]
    if not candidates:
        raise UploadScopeError("Selected project, lab unit, or disease is not allowed for encounter-set upload.", code="mapping_not_found")
    return candidates[0] if disease_id is not None else _select_default_mapping(candidates)


def resolve_default_upload_disease(mapping: UploadScopeMapping) -> int:
    """Return a mapping's default disease ID or raise if not configured."""
    if mapping.default_disease_id is None:
        raise UploadScopeError("No default upload disease is configured for this mapping.", code="default_disease_missing")
    return mapping.default_disease_id


__all__ = [
    "UploadOptions",
    "UploadScopeError",
    "UploadScopeMapping",
    "UploadScopeSelection",
    "get_scoped_mapping_admin_lab_unit_ids",
    "get_user_lab_unit_ids",
    "get_user_lab_unit_ids_no_admin_override",
    "get_user_uploadVerify_eligibility",
    "get_user_upload_mappings",
    "get_user_upload_options",
    "resolve_default_upload_disease",
    "validate_direct_upload_scope",
    "validate_encounter_set_upload_scope",
    "validate_pregraded_upload_scope",
    "validate_remedio_upload_scope",
]
