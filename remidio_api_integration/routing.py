"""Routing service for Remidio API-fetched encounters."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from encounter_set_types.models import EncounterSetType
from models import Camera, LabUnit, Project, RemidioConnection, RemidioExam, RemidioSite
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileEncounterSetType,
)
from upload_profiles.service import UPLOAD_KIND_ENCOUNTER_SET, manager_lab_unit_ids

from .errors import RemidioConfigError
from .models import ProjectUploadProfileRemidioApiBinding, RemidioApiExamEncounter, RemidioApiRoutingProfile, RemidioApiSourceRule
from .validation import normalize_device_type


def list_api_source_rules(db: Session, *, connection_id: int | None = None) -> list[dict[str, Any]]:
    query = db.query(RemidioApiSourceRule).options(
        selectinload(RemidioApiSourceRule.connection),
        selectinload(RemidioApiSourceRule.site),
        selectinload(RemidioApiSourceRule.bindings)
        .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
        .selectinload(ProjectUploadProfile.project),
        selectinload(RemidioApiSourceRule.bindings)
        .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
        .selectinload(ProjectUploadProfile.profile),
        selectinload(RemidioApiSourceRule.bindings)
        .selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit)
        .selectinload(LabUnit.hospital),
        selectinload(RemidioApiSourceRule.bindings).selectinload(ProjectUploadProfileRemidioApiBinding.camera),
    )
    if connection_id is not None:
        query = query.filter(RemidioApiSourceRule.remidio_connection_id == connection_id)
    rows = query.order_by(RemidioApiSourceRule.active.desc(), RemidioApiSourceRule.remidio_connection_id, RemidioApiSourceRule.site_custom_identifier).all()
    return [_source_rule_summary(row) for row in rows]


def list_routing_profiles(db: Session, *, project_id: int | None = None) -> list[dict[str, Any]]:
    query = db.query(RemidioApiRoutingProfile).options(
        selectinload(RemidioApiRoutingProfile.project),
        selectinload(RemidioApiRoutingProfile.routes)
        .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule)
        .selectinload(RemidioApiSourceRule.connection),
        selectinload(RemidioApiRoutingProfile.routes)
        .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule)
        .selectinload(RemidioApiSourceRule.site),
        selectinload(RemidioApiRoutingProfile.routes)
        .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
        .selectinload(ProjectUploadProfile.profile),
        selectinload(RemidioApiRoutingProfile.routes)
        .selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit)
        .selectinload(LabUnit.hospital),
        selectinload(RemidioApiRoutingProfile.routes).selectinload(ProjectUploadProfileRemidioApiBinding.camera),
    )
    if project_id is not None:
        query = query.filter(RemidioApiRoutingProfile.project_id == project_id)
    rows = query.order_by(RemidioApiRoutingProfile.active.desc(), RemidioApiRoutingProfile.name).all()
    return [_routing_profile_summary(row) for row in rows]


def upsert_routing_profile(db: Session, payload: dict[str, Any]) -> RemidioApiRoutingProfile:
    profile_id = _optional_int(payload.get("id") or payload.get("routing_profile_id"))
    project_id = _required_int(payload, "project_id")
    project = db.get(Project, project_id)
    if project is None:
        raise RemidioConfigError("project_id does not exist.")
    name = _required_string(payload, "name")
    active = _optional_bool(payload.get("active"), default=True)

    profile = db.get(RemidioApiRoutingProfile, profile_id) if profile_id else None
    if profile_id and profile is None:
        raise RemidioConfigError("Remidio API routing profile was not found.")
    if profile is None:
        profile = RemidioApiRoutingProfile(project_id=project_id, name=name, active=active)
        db.add(profile)

    was_active = bool(profile.active)
    profile.project_id = project_id
    profile.name = name
    profile.description = (payload.get("description") or "").strip() or None
    profile.active = active
    profile.updated_at = utcnow()
    if was_active and not active:
        _deactivate_routing_profile_routes(profile)
    try:
        db.flush()
    except IntegrityError as exc:
        raise RemidioConfigError("A Remidio API routing profile with this name already exists for the project.") from exc
    return profile


def create_routing_profile_with_route(
    db: Session,
    payload: dict[str, Any],
    *,
    manager_user_id: int | None = None,
) -> tuple[RemidioApiRoutingProfile, ProjectUploadProfileRemidioApiBinding]:
    profile = upsert_routing_profile(db, payload)
    route_payload = dict(payload)
    route_payload["routing_profile_id"] = profile.id
    binding = upsert_routing_profile_route(db, route_payload, manager_user_id=manager_user_id)
    return profile, binding


def delete_routing_profile(db: Session, routing_profile_id: int) -> None:
    profile = db.get(RemidioApiRoutingProfile, routing_profile_id)
    if profile is None:
        raise RemidioConfigError("Remidio API routing profile was not found.")
    for route in list(profile.routes):
        db.delete(route)
    db.delete(profile)
    db.flush()


def set_routing_profile_route_active(
    db: Session,
    route_id: int,
    *,
    active: bool,
    manager_user_id: int | None = None,
) -> ProjectUploadProfileRemidioApiBinding:
    route = db.get(ProjectUploadProfileRemidioApiBinding, route_id)
    if route is None:
        raise RemidioConfigError("Remidio API routing rule was not found.")
    _require_route_lab_scope(route, manager_user_id)
    if not active:
        _deactivate_route(route)
        db.flush()
        return route

    if route.routing_profile and not route.routing_profile.active:
        raise RemidioConfigError("Activate the routing profile before activating this route.")
    _ensure_no_binding_overlap(
        db,
        source_rule_id=route.remidio_api_source_rule_id,
        active_from_date=route.active_from_date,
        active_to_date=route.active_to_date,
        exclude_binding_id=route.id,
    )
    route.active = True
    route.updated_at = utcnow()
    db.flush()
    return route


def delete_routing_profile_route(
    db: Session,
    route_id: int,
    *,
    manager_user_id: int | None = None,
) -> str:
    route = db.get(ProjectUploadProfileRemidioApiBinding, route_id)
    if route is None:
        raise RemidioConfigError("Remidio API routing rule was not found.")
    _require_route_lab_scope(route, manager_user_id)
    linked_encounters = (
        db.query(RemidioApiExamEncounter.id)
        .filter(RemidioApiExamEncounter.remidio_api_binding_id == route.id)
        .first()
    )
    if linked_encounters:
        _deactivate_route(route)
        db.flush()
        return "deactivated"

    db.delete(route)
    db.flush()
    return "deleted"


def upsert_routing_profile_route(
    db: Session,
    payload: dict[str, Any],
    *,
    manager_user_id: int | None = None,
) -> ProjectUploadProfileRemidioApiBinding:
    routing_profile_id = _required_int(payload, "routing_profile_id")
    routing_profile = db.get(RemidioApiRoutingProfile, routing_profile_id)
    if routing_profile is None or not routing_profile.active:
        raise RemidioConfigError("Remidio API routing profile was not found or inactive.")

    project_upload_profile_id = _required_int(payload, "project_upload_profile_id")
    project_profile = _load_project_profile(db, project_upload_profile_id)
    if project_profile.project_id != routing_profile.project_id:
        raise RemidioConfigError("Route target upload profile must belong to the routing profile project.")
    _validate_automated_project_profile(project_profile)

    source_rule = upsert_api_source_rule(
        db,
        {
            "id": payload.get("remidio_api_source_rule_id") or payload.get("source_rule_id"),
            "remidio_connection_id": payload.get("remidio_connection_id"),
            "remidio_site_id": payload.get("remidio_site_id"),
            "site_custom_identifier": payload.get("site_custom_identifier"),
            "remidio_device_type": payload.get("remidio_device_type"),
            "active": True,
        },
    )

    binding_payload = dict(payload)
    binding_payload["project_upload_profile_id"] = project_profile.id
    binding_payload["remidio_api_source_rule_id"] = source_rule.id
    binding = upsert_api_binding(db, binding_payload, manager_user_id=manager_user_id)
    binding.routing_profile_id = routing_profile.id
    binding.updated_at = utcnow()
    db.flush()
    return binding


def upsert_api_source_rule(db: Session, payload: dict[str, Any]) -> RemidioApiSourceRule:
    rule_id = _optional_int(payload.get("id") or payload.get("rule_id"))
    connection_id = _required_int(payload, "remidio_connection_id")
    connection = db.get(RemidioConnection, connection_id)
    if not connection or not connection.active:
        raise RemidioConfigError("Remidio connection was not found or inactive.")

    site_id = _optional_int(payload.get("remidio_site_id"))
    site = None
    if site_id is not None:
        site = db.get(RemidioSite, site_id)
        if site is None or site.remidio_connection_id != connection_id:
            raise RemidioConfigError("remidio_site_id does not belong to the connection.")

    site_custom_identifier = ((site.site_custom_identifier if site else None) or payload.get("site_custom_identifier") or "").strip()
    if not site_custom_identifier:
        raise RemidioConfigError("site_custom_identifier is required.")
    device_type = normalize_device_type(_required_string(payload, "remidio_device_type"))
    active = _optional_bool(payload.get("active"), default=True)

    rule = db.get(RemidioApiSourceRule, rule_id) if rule_id else None
    if rule_id and rule is None:
        raise RemidioConfigError("Remidio API source rule was not found.")
    if rule is None:
        rule = (
            db.query(RemidioApiSourceRule)
            .filter(
                RemidioApiSourceRule.remidio_connection_id == connection_id,
                RemidioApiSourceRule.site_custom_identifier == site_custom_identifier,
                RemidioApiSourceRule.remidio_device_type == device_type,
                RemidioApiSourceRule.active.is_(active),
            )
            .order_by(RemidioApiSourceRule.id.asc())
            .first()
        )
    if rule is None and active:
        rule = (
            db.query(RemidioApiSourceRule)
            .filter(
                RemidioApiSourceRule.remidio_connection_id == connection_id,
                RemidioApiSourceRule.site_custom_identifier == site_custom_identifier,
                RemidioApiSourceRule.remidio_device_type == device_type,
                RemidioApiSourceRule.active.is_(True),
            )
            .order_by(RemidioApiSourceRule.id.asc())
            .first()
        )
    if rule is None:
        rule = RemidioApiSourceRule(
            remidio_connection_id=connection_id,
            site_custom_identifier=site_custom_identifier,
            remidio_device_type=device_type,
            active=active,
        )
        db.add(rule)

    if active:
        with db.no_autoflush:
            conflict = (
                db.query(RemidioApiSourceRule.id)
                .filter(
                    RemidioApiSourceRule.id != (rule.id or 0),
                    RemidioApiSourceRule.remidio_connection_id == connection_id,
                    RemidioApiSourceRule.site_custom_identifier == site_custom_identifier,
                    RemidioApiSourceRule.remidio_device_type == device_type,
                    RemidioApiSourceRule.active.is_(True),
                )
                .first()
            )
        if conflict:
            if rule_id is None:
                existing = db.get(RemidioApiSourceRule, conflict.id)
                if existing is not None:
                    return existing
            raise RemidioConfigError("An active Remidio API source rule already exists for this connection, site, and device.")

    rule.remidio_connection_id = connection_id
    rule.remidio_site_id = site_id
    rule.site_custom_identifier = site_custom_identifier
    rule.remidio_device_type = device_type
    rule.active = active
    rule.updated_at = utcnow()
    try:
        db.flush()
    except IntegrityError as exc:
        raise RemidioConfigError("Remidio API source rule conflicts with an existing active rule.") from exc
    return rule


def list_api_bindings(
    db: Session,
    *,
    project_upload_profile_id: int | None = None,
    source_rule_id: int | None = None,
) -> list[dict[str, Any]]:
    query = db.query(ProjectUploadProfileRemidioApiBinding).options(
        selectinload(ProjectUploadProfileRemidioApiBinding.routing_profile).selectinload(RemidioApiRoutingProfile.project),
        selectinload(ProjectUploadProfileRemidioApiBinding.source_rule).selectinload(RemidioApiSourceRule.connection),
        selectinload(ProjectUploadProfileRemidioApiBinding.source_rule).selectinload(RemidioApiSourceRule.site),
        selectinload(ProjectUploadProfileRemidioApiBinding.project_profile).selectinload(ProjectUploadProfile.project),
        selectinload(ProjectUploadProfileRemidioApiBinding.project_profile).selectinload(ProjectUploadProfile.profile),
        selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit).selectinload(LabUnit.hospital),
        selectinload(ProjectUploadProfileRemidioApiBinding.camera),
    )
    if project_upload_profile_id is not None:
        query = query.filter(ProjectUploadProfileRemidioApiBinding.project_upload_profile_id == project_upload_profile_id)
    if source_rule_id is not None:
        query = query.filter(ProjectUploadProfileRemidioApiBinding.remidio_api_source_rule_id == source_rule_id)
    rows = query.order_by(
        ProjectUploadProfileRemidioApiBinding.active.desc(),
        ProjectUploadProfileRemidioApiBinding.remidio_api_source_rule_id,
        ProjectUploadProfileRemidioApiBinding.active_from_date,
    ).all()
    return [_binding_summary(row) for row in rows]


def upsert_api_binding(
    db: Session,
    payload: dict[str, Any],
    *,
    manager_user_id: int | None = None,
) -> ProjectUploadProfileRemidioApiBinding:
    binding_id = _optional_int(payload.get("id") or payload.get("binding_id"))
    project_upload_profile_id = _required_int(payload, "project_upload_profile_id")
    source_rule_id = _required_int(payload, "remidio_api_source_rule_id")
    lab_unit_id = _required_int(payload, "lab_unit_id")
    camera_id = _required_int(payload, "camera_id")
    active_from_date = _required_date(payload, "active_from_date")
    active_to_date = _optional_date(payload.get("active_to_date"))
    active = _optional_bool(payload.get("active"), default=True)
    if active_to_date is not None and active_to_date < active_from_date:
        raise RemidioConfigError("active_to_date must be on or after active_from_date.")
    if manager_user_id is not None and lab_unit_id not in manager_lab_unit_ids(manager_user_id):
        raise RemidioConfigError("You cannot bind Remidio API routing outside your lab-unit scope.")

    project_profile = _load_project_profile(db, project_upload_profile_id)
    _validate_automated_project_profile(project_profile)
    source_rule = db.get(RemidioApiSourceRule, source_rule_id)
    if source_rule is None or not source_rule.active:
        raise RemidioConfigError("Remidio API source rule was not found or inactive.")
    lab_unit = db.get(LabUnit, lab_unit_id)
    if lab_unit is None:
        raise RemidioConfigError("lab_unit_id does not exist.")
    if db.get(Camera, camera_id) is None:
        raise RemidioConfigError("camera_id does not exist.")

    binding = db.get(ProjectUploadProfileRemidioApiBinding, binding_id) if binding_id else None
    if binding_id and binding is None:
        raise RemidioConfigError("Remidio API project binding was not found.")
    if binding is None:
        binding = ProjectUploadProfileRemidioApiBinding(
            project_upload_profile_id=project_upload_profile_id,
            remidio_api_source_rule_id=source_rule_id,
            active_from_date=active_from_date,
        )
        db.add(binding)

    if active:
        with db.no_autoflush:
            _ensure_no_binding_overlap(
                db,
                source_rule_id=source_rule_id,
                active_from_date=active_from_date,
                active_to_date=active_to_date,
                exclude_binding_id=binding.id,
            )

    binding.project_upload_profile_id = project_upload_profile_id
    binding.remidio_api_source_rule_id = source_rule_id
    if "routing_profile_id" in payload:
        routing_profile_id = _optional_int(payload.get("routing_profile_id"))
        if routing_profile_id is not None:
            routing_profile = db.get(RemidioApiRoutingProfile, routing_profile_id)
            if routing_profile is None:
                raise RemidioConfigError("Remidio API routing profile was not found.")
            if routing_profile.project_id != project_profile.project_id:
                raise RemidioConfigError("Route target upload profile must belong to the routing profile project.")
        binding.routing_profile_id = routing_profile_id
    binding.lab_unit_id = lab_unit_id
    binding.camera_id = camera_id
    binding.active_from_date = active_from_date
    binding.active_to_date = active_to_date
    binding.active = active
    binding.updated_at = utcnow()
    try:
        db.flush()
    except IntegrityError as exc:
        raise RemidioConfigError("Remidio API project binding conflicts with an existing active date window.") from exc
    return binding


def resolve_binding_for_image(
    db: Session,
    *,
    exam: RemidioExam,
    device_type: str | None,
) -> ProjectUploadProfileRemidioApiBinding | None:
    source_rule = resolve_source_rule_for_image(db, exam=exam, device_type=device_type)
    if source_rule is None:
        return None
    candidates = _active_bindings_for_date(db, source_rule_id=source_rule.id, route_date=_route_date(exam))
    if len(candidates) != 1:
        return None
    return candidates[0]


def resolve_source_rule_for_image(db: Session, *, exam: RemidioExam, device_type: str | None) -> RemidioApiSourceRule | None:
    device_text = (device_type or "").strip()
    normalized_device = normalize_device_type(device_text) if device_text else ""
    site_identifier = _site_identifier(exam)
    if not site_identifier or not normalized_device:
        return None
    rules = (
        db.query(RemidioApiSourceRule)
        .filter(
            RemidioApiSourceRule.remidio_connection_id == exam.remidio_connection_id,
            RemidioApiSourceRule.site_custom_identifier == site_identifier,
            RemidioApiSourceRule.remidio_device_type == normalized_device,
            RemidioApiSourceRule.active.is_(True),
        )
        .all()
    )
    return rules[0] if len(rules) == 1 else None


def _active_bindings_for_date(
    db: Session,
    *,
    source_rule_id: int,
    route_date: date,
) -> list[ProjectUploadProfileRemidioApiBinding]:
    return (
        db.query(ProjectUploadProfileRemidioApiBinding)
        .options(
            selectinload(ProjectUploadProfileRemidioApiBinding.project_profile).selectinload(ProjectUploadProfile.project),
            selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
            .selectinload(ProjectUploadProfile.profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.encounter_set_type),
            selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
            .selectinload(ProjectUploadProfile.profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.image_grading_schemes),
            selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
            selectinload(ProjectUploadProfileRemidioApiBinding.camera),
        )
        .outerjoin(RemidioApiRoutingProfile, ProjectUploadProfileRemidioApiBinding.routing_profile_id == RemidioApiRoutingProfile.id)
        .filter(
            ProjectUploadProfileRemidioApiBinding.remidio_api_source_rule_id == source_rule_id,
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
            or_(
                ProjectUploadProfileRemidioApiBinding.routing_profile_id.is_(None),
                RemidioApiRoutingProfile.active.is_(True),
            ),
            ProjectUploadProfileRemidioApiBinding.active_from_date <= route_date,
            or_(
                ProjectUploadProfileRemidioApiBinding.active_to_date.is_(None),
                ProjectUploadProfileRemidioApiBinding.active_to_date >= route_date,
            ),
        )
        .all()
    )


def _ensure_no_binding_overlap(
    db: Session,
    *,
    source_rule_id: int,
    active_from_date: date,
    active_to_date: date | None,
    exclude_binding_id: int | None,
) -> None:
    query = (
        db.query(ProjectUploadProfileRemidioApiBinding.id)
        .outerjoin(RemidioApiRoutingProfile, ProjectUploadProfileRemidioApiBinding.routing_profile_id == RemidioApiRoutingProfile.id)
        .filter(
            ProjectUploadProfileRemidioApiBinding.remidio_api_source_rule_id == source_rule_id,
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
            or_(
                ProjectUploadProfileRemidioApiBinding.routing_profile_id.is_(None),
                RemidioApiRoutingProfile.active.is_(True),
            ),
            ProjectUploadProfileRemidioApiBinding.active_from_date <= (active_to_date or date.max),
            or_(
                ProjectUploadProfileRemidioApiBinding.active_to_date.is_(None),
                ProjectUploadProfileRemidioApiBinding.active_to_date >= active_from_date,
            ),
        )
    )
    if exclude_binding_id:
        query = query.filter(ProjectUploadProfileRemidioApiBinding.id != exclude_binding_id)
    if query.first():
        raise RemidioConfigError("This Remidio API source already has an active binding for an overlapping date window.")


def _deactivate_routing_profile_routes(profile: RemidioApiRoutingProfile) -> None:
    for route in profile.routes:
        _deactivate_route(route)


def _deactivate_route(route: ProjectUploadProfileRemidioApiBinding) -> None:
    if not route.active:
        return
    today = utcnow().date()
    route.active = False
    if route.active_to_date is None or route.active_to_date > today:
        route.active_to_date = today
    route.updated_at = utcnow()


def _require_route_lab_scope(route: ProjectUploadProfileRemidioApiBinding, manager_user_id: int | None) -> None:
    if manager_user_id is not None and route.lab_unit_id not in manager_lab_unit_ids(manager_user_id):
        raise RemidioConfigError("You cannot modify Remidio API routing outside your lab-unit scope.")


def _load_project_profile(db: Session, project_upload_profile_id: int) -> ProjectUploadProfile:
    project_profile = (
        db.execute(
            select(ProjectUploadProfile)
            .options(
                selectinload(ProjectUploadProfile.project),
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.upload_kinds),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.encounter_set_type),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes),
            )
            .where(ProjectUploadProfile.id == project_upload_profile_id)
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if project_profile is None or not project_profile.active:
        raise RemidioConfigError("Project upload profile mapping was not found or inactive.")
    return project_profile


def _validate_automated_project_profile(project_profile: ProjectUploadProfile) -> None:
    profile = project_profile.profile
    if not profile or not profile.active:
        raise RemidioConfigError("Upload profile was not found or inactive.")
    if not profile.automated_remidio_populated:
        raise RemidioConfigError("Remidio API bindings require an automated Remidio-populated upload profile.")
    upload_kinds = {row.upload_kind for row in profile.upload_kinds}
    if upload_kinds != {UPLOAD_KIND_ENCOUNTER_SET}:
        raise RemidioConfigError("Automated Remidio-populated upload profiles must allow only EncounterSet uploads.")
    remidio_configs = [
        config
        for config in profile.encounter_set_types
        if config.active and config.encounter_set_type and config.encounter_set_type.code == "remidio_api_standard"
    ]
    if not remidio_configs:
        raise RemidioConfigError("Automated Remidio-populated upload profiles must include the Remidio API Standard EncounterSetType.")
    if any(not config.default_image_grading_scheme_id or not [row for row in config.image_grading_schemes if row.active] for config in remidio_configs):
        raise RemidioConfigError("Automated Remidio-populated upload profiles require image grading schemes and one default image scheme.")


def _source_rule_summary(rule: RemidioApiSourceRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "remidio_connection_id": rule.remidio_connection_id,
        "connection_name": rule.connection.name if rule.connection else None,
        "remidio_site_id": rule.remidio_site_id,
        "site_name": rule.site.site_name if rule.site else None,
        "site_custom_identifier": rule.site_custom_identifier,
        "remidio_device_type": rule.remidio_device_type,
        "active": rule.active,
        "bindings": [_binding_summary(binding) for binding in rule.bindings if binding.active],
        "created_at": _iso(rule.created_at),
        "updated_at": _iso(rule.updated_at),
    }


def _routing_profile_summary(profile: RemidioApiRoutingProfile) -> dict[str, Any]:
    project = profile.project
    routes = sorted(
        [_binding_summary(binding) for binding in profile.routes],
        key=lambda item: (
            not item["active"],
            item.get("site_custom_identifier") or "",
            item.get("remidio_device_type") or "",
            item.get("active_from_date") or "",
            item["id"] or 0,
        ),
    )
    return {
        "id": profile.id,
        "project_id": profile.project_id,
        "project_title": project.title if project else None,
        "project_code": project.code if project else None,
        "name": profile.name,
        "description": profile.description,
        "active": profile.active,
        "routes": routes,
        "created_at": _iso(profile.created_at),
        "updated_at": _iso(profile.updated_at),
    }


def _binding_summary(binding: ProjectUploadProfileRemidioApiBinding) -> dict[str, Any]:
    project_profile = binding.project_profile
    profile = project_profile.profile if project_profile else None
    project = project_profile.project if project_profile else None
    source_rule = binding.source_rule
    return {
        "id": binding.id,
        "routing_profile_id": binding.routing_profile_id,
        "routing_profile_name": binding.routing_profile.name if binding.routing_profile else None,
        "project_upload_profile_id": binding.project_upload_profile_id,
        "project_id": project_profile.project_id if project_profile else None,
        "project_title": project.title if project else None,
        "upload_profile_id": project_profile.upload_profile_id if project_profile else None,
        "upload_profile_name": profile.name if profile else None,
        "remidio_api_source_rule_id": binding.remidio_api_source_rule_id,
        "remidio_connection_id": source_rule.remidio_connection_id if source_rule else None,
        "connection_name": source_rule.connection.name if source_rule and source_rule.connection else None,
        "remidio_site_id": source_rule.remidio_site_id if source_rule else None,
        "site_name": source_rule.site.site_name if source_rule and source_rule.site else None,
        "site_custom_identifier": source_rule.site_custom_identifier if source_rule else None,
        "remidio_device_type": source_rule.remidio_device_type if source_rule else None,
        "lab_unit_id": binding.lab_unit_id,
        "lab_unit_name": binding.lab_unit.name if binding.lab_unit else None,
        "hospital_id": binding.lab_unit.hospital_id if binding.lab_unit else None,
        "hospital_name": binding.lab_unit.hospital.name if binding.lab_unit and binding.lab_unit.hospital else None,
        "camera_id": binding.camera_id,
        "camera_name": binding.camera.name if binding.camera else None,
        "active_from_date": binding.active_from_date.isoformat() if binding.active_from_date else None,
        "active_to_date": binding.active_to_date.isoformat() if binding.active_to_date else None,
        "active": binding.active,
        "created_at": _iso(binding.created_at),
        "updated_at": _iso(binding.updated_at),
    }


def _site_identifier(exam: RemidioExam) -> str | None:
    if exam.site_custom_identifier:
        return exam.site_custom_identifier
    if exam.site and exam.site.site_custom_identifier:
        return exam.site.site_custom_identifier
    return None


def _route_date(exam: RemidioExam) -> date:
    if exam.exam_date is None:
        return utcnow().date()
    return exam.exam_date.date()


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if value is None or str(value).strip() == "":
        raise RemidioConfigError(f"{field_name} is required.")
    return str(value).strip()


def _required_int(payload: dict[str, Any], field_name: str) -> int:
    value = _optional_int(payload.get(field_name))
    if value is None:
        raise RemidioConfigError(f"{field_name} is required.")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RemidioConfigError("Expected an integer identifier.")


def _required_date(payload: dict[str, Any], field_name: str) -> date:
    value = _optional_date(payload.get(field_name))
    if value is None:
        raise RemidioConfigError(f"{field_name} is required.")
    return value


def _optional_date(value: Any) -> date | None:
    if value in {None, ""}:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise RemidioConfigError("Date values must be YYYY-MM-DD or DD-MM-YYYY.")


def _optional_bool(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _iso(value) -> str | None:
    return value.isoformat() if value else None
