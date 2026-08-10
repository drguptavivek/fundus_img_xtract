"""Mutable EncounterSet grading policy DTOs and frozen runtime snapshots."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import selectinload

from models import Disease, DiseaseGrading
from upload_profiles.models import UploadProfileEncounterSetTypeGradingPackage
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileEncounterSetType


POLICY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EncounterSetScopePolicyDTO:
    scope_disease_id: int | None
    image_grading_scheme_ids: tuple[int, ...]
    encounter_grading_scheme_id: int
    parent_scope_disease_id: int | None
    link_role: str


@dataclass(frozen=True)
class EncounterSetPackagePolicyDTO:
    config_id: int | None
    name: str
    code: str
    applicability: str
    grading_mode: str
    policy_revision: int | None
    root_scope_disease_id: int | None
    scopes: tuple[EncounterSetScopePolicyDTO, ...]
    image_scheme_policies: dict[int, str]
    image_scheme_negative_controls_per_positive: dict[int, int]
    image_scheme_metadata_rules: dict[int, dict[str, str]]
    source: str


class EncounterSetPolicyError(ValueError):
    """Raised when a mutable profile policy cannot create a valid package."""


def package_policy_from_model(
    package: UploadProfileEncounterSetTypeGradingPackage,
) -> EncounterSetPackagePolicyDTO:
    image_scheme_ids = tuple(
        scheme.disease_id for scheme in package.image_grading_schemes if scheme.active
    )
    encounter_scheme_ids = tuple(
        scheme.disease_id for scheme in package.encounter_grading_schemes if scheme.active
    )
    raw_scope_config = package.scope_config_json or {}
    raw_scopes = raw_scope_config.get("scopes")
    scopes: list[EncounterSetScopePolicyDTO] = []
    if isinstance(raw_scopes, list):
        for raw_scope in raw_scopes:
            if not isinstance(raw_scope, dict):
                continue
            encounter_scheme_id = _positive_int(
                raw_scope.get("encounter_grading_scheme_id")
            )
            if encounter_scheme_id is None:
                continue
            scope_disease_id = _positive_int(raw_scope.get("scope_disease_id"))
            scope_image_ids = tuple(
                value
                for value in (
                    _positive_int(item)
                    for item in raw_scope.get("image_grading_scheme_ids", [])
                )
                if value is not None
            )
            scopes.append(
                EncounterSetScopePolicyDTO(
                    scope_disease_id=scope_disease_id,
                    image_grading_scheme_ids=scope_image_ids,
                    encounter_grading_scheme_id=encounter_scheme_id,
                    parent_scope_disease_id=_positive_int(
                        raw_scope.get("parent_scope_disease_id")
                    ),
                    link_role=str(raw_scope.get("link_role") or "root"),
                )
            )

    # Compatibility for policies created before explicit scope DTOs existed.
    if not scopes and package.grading_mode == "unified":
        if len(encounter_scheme_ids) != 1:
            raise EncounterSetPolicyError(
                f"Unified package {package.name} must have exactly one set grading scheme."
            )
        scopes = [
            EncounterSetScopePolicyDTO(
                scope_disease_id=None,
                image_grading_scheme_ids=image_scheme_ids,
                encounter_grading_scheme_id=encounter_scheme_ids[0],
                parent_scope_disease_id=None,
                link_role="unified",
            )
        ]
    elif not scopes and package.grading_mode == "disease_specific":
        if len(image_scheme_ids) != 1 or len(encounter_scheme_ids) != 1:
            raise EncounterSetPolicyError(
                f"Disease package {package.name} is missing its explicit scope mapping."
            )
        scopes = [
            EncounterSetScopePolicyDTO(
                scope_disease_id=image_scheme_ids[0],
                image_grading_scheme_ids=(image_scheme_ids[0],),
                encounter_grading_scheme_id=encounter_scheme_ids[0],
                parent_scope_disease_id=None,
                link_role="root",
            )
        ]

    _validate_scopes(package.grading_mode, scopes)
    root_id = _positive_int(raw_scope_config.get("root_image_grading_scheme_id"))
    if root_id is None:
        root_scope = next((scope for scope in scopes if scope.link_role == "root"), None)
        root_id = root_scope.scope_disease_id if root_scope else None
    return EncounterSetPackagePolicyDTO(
        config_id=package.id,
        name=package.name,
        code=package.code,
        applicability=package.applicability,
        grading_mode=package.grading_mode or "unified",
        policy_revision=package.policy_revision,
        root_scope_disease_id=root_id,
        scopes=tuple(scopes),
        image_scheme_policies={
            scheme.disease_id: scheme.auto_create_policy
            for scheme in package.image_grading_schemes
            if scheme.active
        },
        image_scheme_negative_controls_per_positive={
            scheme.disease_id: scheme.negative_controls_per_positive
            for scheme in package.image_grading_schemes
            if scheme.active
        },
        image_scheme_metadata_rules={
            scheme.disease_id: {
                "field_key": scheme.metadata_field_key,
                "match_value": scheme.metadata_match_value,
            }
            for scheme in package.image_grading_schemes
            if scheme.active and scheme.metadata_field_key and scheme.metadata_match_value
        },
        source="profile_package",
    )


def freeze_policy_snapshot(db, policy: EncounterSetPackagePolicyDTO) -> dict[str, Any]:
    """Copy every grading definition needed by runtime grading and history."""
    disease_ids = {
        disease_id
        for scope in policy.scopes
        for disease_id in (
            *scope.image_grading_scheme_ids,
            scope.encounter_grading_scheme_id,
        )
    }
    diseases = (
        db.query(Disease)
        .options(
            selectinload(Disease.disease_gradings).selectinload(
                DiseaseGrading.features
            )
        )
        .filter(Disease.id.in_(disease_ids))
        .all()
    )
    disease_by_id = {disease.id: disease for disease in diseases}
    if set(disease_by_id) != disease_ids:
        raise EncounterSetPolicyError("A grading scheme in this package no longer exists.")
    definitions = {}
    for disease_id, disease in disease_by_id.items():
        definitions[str(disease_id)] = {
            "id": disease.id,
            "name": disease.name,
            "grading_scope": disease.grading_scope,
            "labels": [
                {
                    "id": label.id,
                    "impression": label.impression,
                    "guidelines": label.guidelines,
                    "is_ungradable": label.is_ungradable,
                    "display_order": label.display_order,
                    "features": [
                        {
                            "id": feature.id,
                            "label": feature.label,
                            "display_order": feature.sr_no,
                        }
                        for feature in sorted(label.features, key=lambda item: item.sr_no)
                    ],
                }
                for label in sorted(
                    (item for item in disease.disease_gradings if item.is_active),
                    key=lambda item: item.display_order,
                )
            ],
        }
    return {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_revision": policy.policy_revision,
        "package": asdict(policy),
        "grading_definitions": definitions,
    }


def effective_project_policy_dto(db, project_id: int) -> dict[str, Any]:
    """Expose the inferred future-task policy independently of runtime history."""
    mappings = (
        db.query(ProjectUploadProfile)
        .join(ProjectUploadProfile.profile)
        .options(
            selectinload(ProjectUploadProfile.profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.encounter_set_type),
            selectinload(ProjectUploadProfile.profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.grading_packages)
            .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes),
            selectinload(ProjectUploadProfile.profile)
            .selectinload(UploadProfile.encounter_set_types)
            .selectinload(UploadProfileEncounterSetType.grading_packages)
            .selectinload(UploadProfileEncounterSetTypeGradingPackage.encounter_grading_schemes),
        )
        .filter(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
        )
        .all()
    )
    packages = []
    warnings = []
    for mapping in mappings:
        for est_config in mapping.profile.encounter_set_types:
            if not est_config.active:
                continue
            for package in est_config.grading_packages:
                if not package.active:
                    continue
                try:
                    policy = package_policy_from_model(package)
                except EncounterSetPolicyError as exc:
                    warnings.append({
                        "code": "incomplete_encounter_set_policy",
                        "profile_id": mapping.profile.id,
                        "package_id": package.id,
                        "message": str(exc),
                    })
                    continue
                packages.append({
                    "profile": {"id": mapping.profile.id, "name": mapping.profile.name},
                    "encounter_set_type": {
                        "id": est_config.encounter_set_type_id,
                        "name": est_config.encounter_set_type.name,
                    },
                    "package": asdict(policy),
                })
    return {"project_id": project_id, "packages": packages, "warnings": warnings}


def _validate_scopes(
    grading_mode: str, scopes: list[EncounterSetScopePolicyDTO]
) -> None:
    if grading_mode == "unified":
        if len(scopes) != 1 or scopes[0].scope_disease_id is not None:
            raise EncounterSetPolicyError(
                "A unified package must contain exactly one unified set scope."
            )
        return
    if not scopes or any(scope.scope_disease_id is None for scope in scopes):
        raise EncounterSetPolicyError(
            "A disease-specific package requires explicit disease set scopes."
        )
    disease_ids = [scope.scope_disease_id for scope in scopes]
    if len(set(disease_ids)) != len(disease_ids):
        raise EncounterSetPolicyError("Disease set scopes must be unique in a package.")
    if sum(scope.link_role == "root" for scope in scopes) != 1:
        raise EncounterSetPolicyError(
            "A disease-specific package must contain exactly one root scope."
        )


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
