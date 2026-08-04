"""Portable project annotation and classification schema export."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
import tomli_w

from models import Disease, DiseaseGrading, Project
from project_annotations.service import get_project_policy_configuration
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeGradingPackage,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileEncounterSetTypePackageEncounterScheme,
    UploadProfileEncounterSetTypePackageImageScheme,
)


PROJECT_SCHEMA_VERSION = 1


def build_project_schema_export(
    db,
    *,
    project_id: int,
    actor_user_id: int,
) -> dict[str, Any]:
    """Return one detached, deterministic project schema document."""
    annotation_schema = get_project_policy_configuration(
        db,
        project_id,
        actor_user_id=actor_user_id,
    ).to_dict()
    project = db.get(Project, project_id)
    associations = _classification_associations(db, project_id=project_id)
    schemes = _classification_schemas(db, associations=associations)
    return {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {
            "id": project.id,
            "code": project.code,
            "title": project.title,
            "active": bool(project.active),
        },
        "annotation_schema": annotation_schema,
        "classification_schemas": schemes,
    }


def project_schema_filename(project_code: str, export_format: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", project_code.strip().lower()).strip("-")
    stem = normalized or "project"
    return f"{stem}-annotation-classification-schema.{export_format}"


def serialize_project_schema_toml(schema: dict[str, Any]) -> str:
    """Serialize the null-free portable schema document as TOML."""
    return tomli_w.dumps(schema, multiline_strings=True)


def _classification_associations(db, *, project_id: int) -> dict[int, list[dict[str, Any]]]:
    associations: dict[int, list[dict[str, Any]]] = {}

    direct_rows = db.execute(
        select(
            UploadProfileDisease.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfileDisease.is_default,
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileDisease.upload_profile_id)
        .join(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
        )
    ).all()
    for scheme_id, profile_id, profile_name, is_default in direct_rows:
        _add_association(
            associations,
            scheme_id,
            {
                "kind": "upload_profile_disease",
                "upload_profile_id": profile_id,
                "upload_profile_name": profile_name,
                "is_default": bool(is_default),
            },
        )

    image_rows = db.execute(
        select(
            UploadProfileEncounterSetTypeImageGradingScheme.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfileEncounterSetType.encounter_set_type_id,
            UploadProfileEncounterSetTypeImageGradingScheme.is_default,
        )
        .join(
            UploadProfileEncounterSetType,
            UploadProfileEncounterSetType.id
            == UploadProfileEncounterSetTypeImageGradingScheme.upload_profile_encounter_set_type_id,
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileEncounterSetType.upload_profile_id)
        .join(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
            UploadProfileEncounterSetType.active.is_(True),
            UploadProfileEncounterSetTypeImageGradingScheme.active.is_(True),
        )
    ).all()
    for scheme_id, profile_id, profile_name, type_id, is_default in image_rows:
        _add_association(
            associations,
            scheme_id,
            {
                "kind": "encounter_set_image",
                "upload_profile_id": profile_id,
                "upload_profile_name": profile_name,
                "encounter_set_type_id": type_id,
                "is_default": bool(is_default),
            },
        )

    encounter_rows = db.execute(
        select(
            UploadProfileEncounterSetType.encounter_grading_scheme_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfileEncounterSetType.encounter_set_type_id,
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileEncounterSetType.upload_profile_id)
        .join(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
            UploadProfileEncounterSetType.active.is_(True),
            UploadProfileEncounterSetType.encounter_grading_scheme_id.is_not(None),
        )
    ).all()
    for scheme_id, profile_id, profile_name, type_id in encounter_rows:
        _add_association(
            associations,
            scheme_id,
            {
                "kind": "encounter_set_encounter",
                "upload_profile_id": profile_id,
                "upload_profile_name": profile_name,
                "encounter_set_type_id": type_id,
            },
        )

    package_image_rows = db.execute(
        select(
            UploadProfileEncounterSetTypePackageImageScheme.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfileEncounterSetType.encounter_set_type_id,
            UploadProfileEncounterSetTypeGradingPackage.code,
            UploadProfileEncounterSetTypePackageImageScheme.is_default,
        )
        .join(
            UploadProfileEncounterSetTypeGradingPackage,
            UploadProfileEncounterSetTypeGradingPackage.id
            == UploadProfileEncounterSetTypePackageImageScheme.package_id,
        )
        .join(
            UploadProfileEncounterSetType,
            UploadProfileEncounterSetType.id
            == UploadProfileEncounterSetTypeGradingPackage.upload_profile_encounter_set_type_id,
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileEncounterSetType.upload_profile_id)
        .join(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
            UploadProfileEncounterSetType.active.is_(True),
            UploadProfileEncounterSetTypeGradingPackage.active.is_(True),
            UploadProfileEncounterSetTypePackageImageScheme.active.is_(True),
        )
    ).all()
    for scheme_id, profile_id, profile_name, type_id, package_code, is_default in package_image_rows:
        _add_association(
            associations,
            scheme_id,
            {
                "kind": "grading_package_image",
                "upload_profile_id": profile_id,
                "upload_profile_name": profile_name,
                "encounter_set_type_id": type_id,
                "package_code": package_code,
                "is_default": bool(is_default),
            },
        )

    package_encounter_rows = db.execute(
        select(
            UploadProfileEncounterSetTypePackageEncounterScheme.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfileEncounterSetType.encounter_set_type_id,
            UploadProfileEncounterSetTypeGradingPackage.code,
        )
        .join(
            UploadProfileEncounterSetTypeGradingPackage,
            UploadProfileEncounterSetTypeGradingPackage.id
            == UploadProfileEncounterSetTypePackageEncounterScheme.package_id,
        )
        .join(
            UploadProfileEncounterSetType,
            UploadProfileEncounterSetType.id
            == UploadProfileEncounterSetTypeGradingPackage.upload_profile_encounter_set_type_id,
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileEncounterSetType.upload_profile_id)
        .join(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
            UploadProfileEncounterSetType.active.is_(True),
            UploadProfileEncounterSetTypeGradingPackage.active.is_(True),
            UploadProfileEncounterSetTypePackageEncounterScheme.active.is_(True),
        )
    ).all()
    for scheme_id, profile_id, profile_name, type_id, package_code in package_encounter_rows:
        _add_association(
            associations,
            scheme_id,
            {
                "kind": "grading_package_encounter",
                "upload_profile_id": profile_id,
                "upload_profile_name": profile_name,
                "encounter_set_type_id": type_id,
                "package_code": package_code,
            },
        )

    for rows in associations.values():
        rows.sort(key=_association_sort_key)
    return associations


def _add_association(
    associations: dict[int, list[dict[str, Any]]],
    scheme_id: int,
    association: dict[str, Any],
) -> None:
    rows = associations.setdefault(int(scheme_id), [])
    if association not in rows:
        rows.append(association)


def _association_sort_key(row: dict[str, Any]) -> tuple:
    return (
        row["kind"],
        row["upload_profile_name"].casefold(),
        row["upload_profile_id"],
        row.get("encounter_set_type_id", 0),
        row.get("package_code", ""),
    )


def _classification_schemas(
    db,
    *,
    associations: dict[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if not associations:
        return []
    schemes = (
        db.execute(
            select(Disease)
            .options(
                selectinload(Disease.disease_gradings).selectinload(DiseaseGrading.features)
            )
            .where(Disease.id.in_(associations))
            .order_by(Disease.name.asc(), Disease.id.asc())
        )
        .scalars()
        .all()
    )
    return [_classification_schema(scheme, associations[scheme.id]) for scheme in schemes]


def _classification_schema(
    scheme: Disease,
    associations: list[dict[str, Any]],
) -> dict[str, Any]:
    grades: list[dict[str, Any]] = []
    for grade in sorted(scheme.disease_gradings or [], key=lambda item: (item.display_order, item.id)):
        grade_payload: dict[str, Any] = {
            "id": grade.id,
            "impression": grade.impression,
            "display_order": grade.display_order,
            "is_active": bool(grade.is_active),
            "prioritize_for_task_selection": bool(grade.prioritize_for_task_selection),
            "is_ungradable": bool(grade.is_ungradable),
            "features": [
                {
                    "id": feature.id,
                    "sr_no": feature.sr_no,
                    "label": feature.label,
                }
                for feature in sorted(grade.features or [], key=lambda item: (item.sr_no, item.id))
            ],
        }
        if grade.guidelines:
            grade_payload["guidelines"] = grade.guidelines
        grades.append(grade_payload)
    return {
        "id": scheme.id,
        "name": scheme.name,
        "grading_scope": scheme.grading_scope,
        "remidio_ocr_linkage": scheme.remidio_ocr_linkage or "none",
        "associations": associations,
        "grades": grades,
    }
