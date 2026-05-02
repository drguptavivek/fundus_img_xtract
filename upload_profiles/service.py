"""Upload profile service interfaces and detached-safe DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession, selectinload

from db_transaction_manager import get_db_session
from models import Area, Camera, LabUnit, Project, User, user_lab_units
from upload_profiles.models import (
    UploadProfile,
    UploadProfileAIWorkflow,
    UploadProfileArea,
    UploadProfileAssignment,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)

UPLOAD_KIND_DIRECT_IMAGE = "direct_image"
UPLOAD_KIND_PREGRADED = "pregraded"
UPLOAD_KIND_REMIDIO = "remidio"
UPLOAD_KIND_ENCOUNTER_SET = "encounter_set"


class UploadProfileError(ValueError):
    """Safe upload-profile validation error for route/API responses."""

    def __init__(self, message: str, *, code: str = "invalid_upload_profile") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class UploadSelection:
    """Normalized selected upload target."""

    project_id: int
    lab_unit_id: int
    disease_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool
    profile_id: int | None = None


@dataclass(frozen=True)
class UploadProfileDTO:
    """Detached-safe upload profile with allowed option IDs."""

    profile_id: int
    name: str
    description: str | None
    project_id: int
    project_title: str
    project_code: str
    lab_unit_id: int
    lab_unit_name: str
    hospital_id: int
    disease_ids: frozenset[int]
    disease_names: dict[int, str]
    default_disease_ids: frozenset[int]
    camera_ids: frozenset[int]
    area_ids: frozenset[int]
    upload_kinds: frozenset[str]
    ai_workflows: tuple[dict[str, Any], ...]
    allow_mydriatic: bool
    allow_non_mydriatic: bool
    default_is_mydriatic: bool

    @property
    def disease_id(self) -> int:
        """Single selected disease for upload paths that accept one disease."""
        return next(iter(sorted(self.disease_ids)))

    @property
    def disease_name(self) -> str:
        return self.disease_names.get(self.disease_id, "")

    @property
    def default_disease_id(self) -> int | None:
        if not self.default_disease_ids:
            return None
        return next(iter(sorted(self.default_disease_ids)))

    @property
    def default_disease_name(self) -> str | None:
        disease_id = self.default_disease_id
        return self.disease_names.get(disease_id) if disease_id else None

    @property
    def allowed_camera_ids(self) -> frozenset[int]:
        return self.camera_ids

    @property
    def allowed_area_ids(self) -> frozenset[int]:
        return self.area_ids


@dataclass(frozen=True)
class UploadOptions:
    """UI/API-ready upload profile options."""

    projects: list[dict[str, Any]]
    lab_units: list[dict[str, Any]]
    diseases: list[dict[str, Any]]
    cameras: list[dict[str, Any]]
    areas: list[dict[str, Any]]
    profiles: list[dict[str, Any]]


def explicit_lab_unit_ids(db: OrmSession, user_id: int) -> set[int]:
    """Return explicitly assigned lab units without role/admin expansion."""
    user = (
        db.execute(
            select(User)
            .options(selectinload(User.lab_units))
            .where(User.id == user_id)
        )
        .scalars()
        .one_or_none()
    )
    if not user:
        return set()
    return {lab_unit.id for lab_unit in user.lab_units or []}


def manager_lab_unit_ids(manager_user_id: int) -> set[int]:
    """Return lab units a manager may administer for upload profiles."""
    with get_db_session() as db:
        return explicit_lab_unit_ids(db, manager_user_id)


def get_user_lab_unit_ids(user_id: int) -> set[int]:
    """Return lab-unit IDs a user may access, preserving legacy admin expansion."""
    with get_db_session() as db:
        user = (
            db.execute(
                select(User)
                .options(selectinload(User.lab_units), selectinload(User.roles))
                .where(User.id == user_id)
            )
            .scalars()
            .one_or_none()
        )
        if not user:
            return set()
        if any(role.name == "admin" for role in (user.roles or [])):
            return {row[0] for row in db.execute(select(LabUnit.id)).all()}
        return {lab_unit.id for lab_unit in user.lab_units or []}


def get_user_upload_profiles(db: OrmSession, user_id: int) -> list[UploadProfileDTO]:
    """Return active upload profiles assigned to a user as detached-safe DTOs."""
    explicit_labs = explicit_lab_unit_ids(db, user_id)
    if not explicit_labs:
        return []
    profiles = (
        db.execute(
            select(UploadProfile)
            .join(UploadProfileAssignment, UploadProfileAssignment.upload_profile_id == UploadProfile.id)
            .join(Project, UploadProfile.project_id == Project.id)
            .where(
                UploadProfileAssignment.user_id == user_id,
                UploadProfileAssignment.active.is_(True),
                UploadProfile.lab_unit_id.in_(explicit_labs),
                UploadProfile.active.is_(True),
                Project.active.is_(True),
            )
            .options(
                selectinload(UploadProfile.project),
                selectinload(UploadProfile.lab_unit),
                selectinload(UploadProfile.diseases).selectinload(UploadProfileDisease.disease),
                selectinload(UploadProfile.cameras).selectinload(UploadProfileCamera.camera),
                selectinload(UploadProfile.areas).selectinload(UploadProfileArea.area),
                selectinload(UploadProfile.upload_kinds),
                selectinload(UploadProfile.ai_workflows).selectinload(UploadProfileAIWorkflow.ai_model),
            )
            .order_by(UploadProfile.project_id, UploadProfile.lab_unit_id, UploadProfile.name)
        )
        .scalars()
        .unique()
        .all()
    )
    return [_profile_to_dto(profile) for profile in profiles]


def get_user_upload_options(db: OrmSession, user_id: int) -> UploadOptions:
    """Return UI-ready upload options for the user's active profiles."""
    return _build_upload_options(db, get_user_upload_profiles(db, user_id))


def get_user_upload_options_for_kind(db: OrmSession, user_id: int, upload_kind: str) -> UploadOptions:
    """Return UI-ready upload options for profiles that allow one upload kind."""
    profiles = [profile for profile in get_user_upload_profiles(db, user_id) if upload_kind in profile.upload_kinds]
    return _build_upload_options(db, profiles)


def filter_upload_options(
    db: OrmSession,
    options: UploadOptions,
    *,
    disease_id: int | None = None,
    disease_name: str | None = None,
    project_id: int | None = None,
    lab_unit_id: int | None = None,
) -> UploadOptions:
    """Filter upload options by profile attributes and rebuild dependent lists."""
    del db
    disease_name = disease_name.strip().lower() if disease_name else None
    disease_name_by_id = {item["id"]: str(item["name"]).lower() for item in options.diseases}
    profiles = [
        profile
        for profile in options.profiles
        if (disease_id is None or disease_id in profile["disease_ids"])
        and (not disease_name or any(disease_name_by_id.get(item) == disease_name for item in profile["disease_ids"]))
        and (project_id is None or profile["project_id"] == project_id)
        and (lab_unit_id is None or profile["lab_unit_id"] == lab_unit_id)
    ]
    return _build_upload_options_from_payloads(options, profiles)


def validate_direct_upload_scope(db: OrmSession, user_id: int, selection: UploadSelection) -> UploadProfileDTO:
    """Validate a direct image upload selection and return the matching profile."""
    return validate_upload_scope(db, user_id, selection, upload_kind=UPLOAD_KIND_DIRECT_IMAGE)


def validate_pregraded_upload_scope(db: OrmSession, user_id: int, selection: UploadSelection) -> UploadProfileDTO:
    """Validate a pregraded upload selection and return the matching profile."""
    return validate_upload_scope(db, user_id, selection, upload_kind=UPLOAD_KIND_PREGRADED)


def validate_remedio_upload_scope(
    db: OrmSession,
    user_id: int,
    project_id: int,
    lab_unit_id: int,
    camera_id: int,
) -> UploadProfileDTO:
    """Validate Remidio upload scope and return a default-disease profile."""
    profiles = [
        profile
        for profile in _candidate_profiles(db, user_id, project_id=project_id, lab_unit_id=lab_unit_id)
        if UPLOAD_KIND_REMIDIO in profile.upload_kinds and camera_id in profile.camera_ids
    ]
    if not profiles:
        raise UploadProfileError("Selected project, lab unit, or camera is not allowed for ZIP upload.", code="profile_not_found")
    return _select_default_profile(profiles)


def validate_encounter_set_upload_scope(
    db: OrmSession,
    user_id: int,
    project_id: int,
    lab_unit_id: int,
    disease_id: int | None = None,
) -> UploadProfileDTO:
    """Validate encounter-set upload scope and return the target profile."""
    profiles = [
        profile
        for profile in _candidate_profiles(db, user_id, project_id=project_id, lab_unit_id=lab_unit_id)
        if UPLOAD_KIND_ENCOUNTER_SET in profile.upload_kinds
    ]
    if disease_id is not None:
        profiles = [profile for profile in profiles if disease_id in profile.disease_ids]
    if not profiles:
        raise UploadProfileError("Selected project, lab unit, or disease is not allowed for encounter-set upload.", code="profile_not_found")
    return profiles[0]


def validate_profile_upload_scope(
    db: OrmSession,
    user_id: int,
    *,
    profile_id: int,
    upload_kind: str,
    disease_id: int | None = None,
    camera_id: int | None = None,
    area_id: int | None = None,
    is_mydriatic: bool | None = None,
) -> UploadProfileDTO:
    """Validate a concrete upload profile selection."""
    profiles = [profile for profile in get_user_upload_profiles(db, user_id) if profile.profile_id == profile_id]
    if not profiles:
        raise UploadProfileError("Selected upload profile is not assigned to this user.", code="profile_not_found")
    profile = profiles[0]
    if upload_kind not in profile.upload_kinds:
        raise UploadProfileError("Selected upload profile does not allow this upload type.", code="upload_kind_not_allowed")
    if disease_id is not None and disease_id not in profile.disease_ids:
        raise UploadProfileError("Selected disease is not allowed for this upload profile.", code="disease_not_allowed")
    if camera_id is not None and camera_id not in profile.camera_ids:
        raise UploadProfileError("Selected camera is not allowed for this upload profile.", code="camera_not_allowed")
    if area_id is not None and area_id not in profile.area_ids:
        raise UploadProfileError("Selected site is not allowed for this upload profile.", code="area_not_allowed")
    if is_mydriatic is not None:
        _validate_mydriatic(profile, is_mydriatic)
    return profile


def validate_upload_scope(
    db: OrmSession,
    user_id: int,
    selection: UploadSelection,
    *,
    upload_kind: str,
) -> UploadProfileDTO:
    """Validate a profile upload selection for an upload kind."""
    candidates = [
        profile
        for profile in _candidate_profiles(db, user_id, project_id=selection.project_id, lab_unit_id=selection.lab_unit_id)
        if upload_kind in profile.upload_kinds
        and selection.disease_id in profile.disease_ids
        and selection.camera_id in profile.camera_ids
        and selection.area_id in profile.area_ids
        and (selection.profile_id is None or selection.profile_id == profile.profile_id)
    ]
    if not candidates:
        raise UploadProfileError("Selected upload profile, disease, camera, or site is not allowed.", code="profile_not_found")
    profile = candidates[0]
    _validate_mydriatic(profile, selection.is_mydriatic)
    return profile


def resolve_default_upload_disease(profile: UploadProfileDTO) -> int:
    """Return a profile default disease ID or raise when not configured."""
    if profile.default_disease_id is None:
        raise UploadProfileError("No default upload disease is configured for this profile.", code="default_disease_missing")
    return profile.default_disease_id


def _candidate_profiles(db: OrmSession, user_id: int, *, project_id: int, lab_unit_id: int) -> list[UploadProfileDTO]:
    if lab_unit_id not in explicit_lab_unit_ids(db, user_id):
        raise UploadProfileError("You don't have upload access to the selected lab unit.", code="lab_unit_not_allowed")
    return [
        profile
        for profile in get_user_upload_profiles(db, user_id)
        if profile.project_id == project_id and profile.lab_unit_id == lab_unit_id
    ]


def _validate_mydriatic(profile: UploadProfileDTO, is_mydriatic: bool) -> None:
    if is_mydriatic and not profile.allow_mydriatic:
        raise UploadProfileError("Mydriatic uploads are not allowed for this profile.", code="mydriatic_not_allowed")
    if not is_mydriatic and not profile.allow_non_mydriatic:
        raise UploadProfileError("Non-mydriatic uploads are not allowed for this profile.", code="non_mydriatic_not_allowed")


def _select_default_profile(profiles: list[UploadProfileDTO]) -> UploadProfileDTO:
    with_defaults = [profile for profile in profiles if profile.default_disease_ids]
    if not with_defaults:
        raise UploadProfileError("No default upload disease is configured for this project and lab unit.", code="default_disease_missing")
    default_ids = {disease_id for profile in with_defaults for disease_id in profile.default_disease_ids}
    if len(default_ids) > 1:
        raise UploadProfileError("Multiple default upload diseases are configured for this project and lab unit.", code="default_disease_ambiguous")
    return with_defaults[0]


def _profile_to_dto(profile: UploadProfile) -> UploadProfileDTO:
    disease_names = {row.disease_id: row.disease.name for row in profile.diseases}
    ai_workflows = tuple(
        {
            "id": row.id,
            "disease_id": row.disease_id,
            "ai_model_id": row.ai_model_id,
            "ai_model_name": row.ai_model.name,
            "upload_kind": row.upload_kind,
            "active": row.active,
        }
        for row in profile.ai_workflows
        if row.active
    )
    return UploadProfileDTO(
        profile_id=profile.id,
        name=profile.name,
        description=profile.description,
        project_id=profile.project_id,
        project_title=profile.project.title,
        project_code=profile.project.code,
        lab_unit_id=profile.lab_unit_id,
        lab_unit_name=profile.lab_unit.name,
        hospital_id=profile.lab_unit.hospital_id,
        disease_ids=frozenset(row.disease_id for row in profile.diseases),
        disease_names=disease_names,
        default_disease_ids=frozenset(row.disease_id for row in profile.diseases if row.is_default),
        camera_ids=frozenset(row.camera_id for row in profile.cameras),
        area_ids=frozenset(row.area_id for row in profile.areas),
        upload_kinds=frozenset(row.upload_kind for row in profile.upload_kinds),
        ai_workflows=ai_workflows,
        allow_mydriatic=profile.allow_mydriatic,
        allow_non_mydriatic=profile.allow_non_mydriatic,
        default_is_mydriatic=profile.default_is_mydriatic,
    )


def _build_upload_options(db: OrmSession, profiles: list[UploadProfileDTO]) -> UploadOptions:
    project_map: dict[int, dict[str, Any]] = {}
    lab_map: dict[int, dict[str, Any]] = {}
    disease_map: dict[int, dict[str, Any]] = {}
    camera_ids: set[int] = set()
    area_ids: set[int] = set()

    for profile in profiles:
        project_map[profile.project_id] = {"id": profile.project_id, "title": profile.project_title, "code": profile.project_code}
        lab_map[profile.lab_unit_id] = {"id": profile.lab_unit_id, "name": profile.lab_unit_name, "hospital_id": profile.hospital_id}
        for disease_id, disease_name in profile.disease_names.items():
            disease_map[disease_id] = {"id": disease_id, "name": disease_name}
        camera_ids.update(profile.camera_ids)
        area_ids.update(profile.area_ids)

    cameras = [
        {"id": camera.id, "name": camera.name}
        for camera in db.execute(select(Camera).where(Camera.id.in_(camera_ids or {-1})).order_by(Camera.name)).scalars().all()
    ]
    areas = [
        {"id": area.id, "name": area.name}
        for area in db.execute(select(Area).where(Area.id.in_(area_ids or {-1})).order_by(Area.name)).scalars().all()
    ]
    payloads = [_profile_payload(profile) for profile in profiles]
    return UploadOptions(
        projects=sorted(project_map.values(), key=lambda item: (item["title"], item["id"])),
        lab_units=sorted(lab_map.values(), key=lambda item: (item["hospital_id"], item["name"], item["id"])),
        diseases=sorted(disease_map.values(), key=lambda item: (item["name"], item["id"])),
        cameras=cameras,
        areas=areas,
        profiles=payloads,
    )


def _build_upload_options_from_payloads(options: UploadOptions, profiles: list[dict[str, Any]]) -> UploadOptions:
    project_ids = {profile["project_id"] for profile in profiles}
    lab_unit_ids = {profile["lab_unit_id"] for profile in profiles}
    disease_ids = {disease_id for profile in profiles for disease_id in profile["disease_ids"]}
    camera_ids = {camera_id for profile in profiles for camera_id in profile["camera_ids"]}
    area_ids = {area_id for profile in profiles for area_id in profile["area_ids"]}
    return UploadOptions(
        projects=sorted([item for item in options.projects if item["id"] in project_ids], key=lambda item: (item["title"], item["id"])),
        lab_units=sorted([item for item in options.lab_units if item["id"] in lab_unit_ids], key=lambda item: (item["hospital_id"], item["name"], item["id"])),
        diseases=sorted([item for item in options.diseases if item["id"] in disease_ids], key=lambda item: (item["name"], item["id"])),
        cameras=[item for item in options.cameras if item["id"] in camera_ids],
        areas=[item for item in options.areas if item["id"] in area_ids],
        profiles=profiles,
    )


def _profile_payload(profile: UploadProfileDTO) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "description": profile.description,
        "project_id": profile.project_id,
        "lab_unit_id": profile.lab_unit_id,
        "disease_ids": sorted(profile.disease_ids),
        "disease_id": profile.disease_id,
        "default_disease_ids": sorted(profile.default_disease_ids),
        "default_disease_id": profile.default_disease_id,
        "camera_ids": sorted(profile.camera_ids),
        "area_ids": sorted(profile.area_ids),
        "upload_kinds": sorted(profile.upload_kinds),
        "ai_workflows": list(profile.ai_workflows),
        "allow_mydriatic": profile.allow_mydriatic,
        "allow_non_mydriatic": profile.allow_non_mydriatic,
        "default_is_mydriatic": profile.default_is_mydriatic,
    }
