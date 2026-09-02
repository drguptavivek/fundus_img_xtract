"""Demo workbench for the grader PWA: a synthetic encounter set, real schemes.

The demo renders the ordinary workbench body over four generated fundus views
(right and left eye, one disc-centred and one macula-centred each) with an
encounter-level target per disease, exactly like a package-workflow session.
Grade options and features come from the diseases configured in the database
so the demo shows the deployment's own DR and glaucoma schemes; a deployment
without those diseases falls back to a built-in set. Nothing is leased or
saved: the session controller answers every API call locally in demo mode.

Images are produced by ``scripts/make_demo_fundus.py`` and contain no patient data.
"""

from __future__ import annotations

from datetime import timedelta

from flask import url_for
from sqlalchemy import select

from auth.utils import utcnow
from grading.workbench.contracts import (
    WorkbenchAnnotationDTO,
    WorkbenchDTO,
    WorkbenchFeatureDTO,
    WorkbenchGradeOptionDTO,
    WorkbenchLeaseDTO,
    WorkbenchMediaDTO,
    WorkbenchPanelDTO,
    WorkbenchSourceDTO,
)
from models import Disease, DiseaseGrading
from project_annotations.contracts import NON_PROJECT_POLICY_REVISION, SUPPORTED_TOOL_KEYS

DEMO_SESSION_UUID = "demo"
DEMO_IMAGE_SIZE = 1400

# (image-level disease, encounter-level disease) as named in the database.
DEMO_SCOPES: tuple[tuple[str, str], ...] = (
    ("DR", "DR Encounter Status"),
    ("Glaucoma", "Glaucoma Encounter Status"),
)

# position, laterality, file, view label. Right eye: macula temporal (left of
# the disc in the image); left eye mirrored.
DEMO_IMAGES: tuple[tuple[int, str, str, str], ...] = (
    (1, "OD", "od-disc.png", "Disc-centred"),
    (2, "OD", "od-macula.png", "Macula-centred"),
    (3, "OS", "os-disc.png", "Disc-centred"),
    (4, "OS", "os-macula.png", "Macula-centred"),
)

_FALLBACK_GRADES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "DR": (
        ("No DR", ()),
        ("Mild DR", ("Microaneurysms", "Dot haemorrhages")),
        ("Moderate NPDR", ("Haemorrhages", "Hard exudates", "Cotton wool spots")),
        ("Severe NPDR", ("Venous beading", "IRMA")),
        ("PDR", ("Neovascularisation", "Vitreous haemorrhage")),
        ("Not Gradable", ()),
    ),
    "DR Encounter Status": (("Normal", ()), ("Abnormal", ()), ("Cannot Grade", ())),
    "Glaucoma": (
        ("Normal", ()),
        ("Suspect", ("Increased CDR", "Rim thinning", "Disc haemorrhage")),
        ("Glaucoma", ("Notching", "RNFL defect")),
        ("Not Gradable", ()),
    ),
    "Glaucoma Encounter Status": (("Normal", ()), ("Glaucoma/Suspect", ()), ("Cannot Grade", ())),
}


def _grade_options(db, disease_name: str, fallback_disease_id: int) -> tuple[int, tuple[WorkbenchGradeOptionDTO, ...]]:
    """Active grades for a configured disease, else the built-in fallback set."""
    disease = db.execute(select(Disease).where(Disease.name == disease_name)).scalar_one_or_none()
    if disease is not None:
        labels = (
            db.execute(
                select(DiseaseGrading)
                .where(DiseaseGrading.disease_id == disease.id, DiseaseGrading.is_active.is_(True))
                .order_by(DiseaseGrading.display_order, DiseaseGrading.id)
            )
            .scalars()
            .all()
        )
        if labels:
            return disease.id, tuple(
                WorkbenchGradeOptionDTO(
                    id=label.id,
                    impression=label.impression,
                    guidelines=label.guidelines,
                    features=tuple(
                        WorkbenchFeatureDTO(id=item.id, label=item.label, sr_no=item.sr_no)
                        for item in sorted(label.features or [], key=lambda value: (value.sr_no or 0, value.id))
                    ),
                )
                for label in labels
            )
    # Synthetic ids are negative so they can never collide with real rows.
    base = -1000 * fallback_disease_id
    return fallback_disease_id, tuple(
        WorkbenchGradeOptionDTO(
            id=base - index,
            impression=impression,
            guidelines=None,
            features=tuple(
                WorkbenchFeatureDTO(id=base - index * 10 - feature_index, label=label, sr_no=feature_index)
                for feature_index, label in enumerate(features, start=1)
            ),
        )
        for index, (impression, features) in enumerate(_FALLBACK_GRADES.get(disease_name, (("Normal", ()), ("Abnormal", ()))), start=1)
    )


def _annotation() -> WorkbenchAnnotationDTO:
    return WorkbenchAnnotationDTO(
        enabled=True,
        policy_source="non_project_default",
        project_id=None,
        policy_revision=NON_PROJECT_POLICY_REVISION,
        enabled_tools=SUPPORTED_TOOL_KEYS,
        default_feature_policy={
            "localization": "box_or_segmentation",
            "preferred_tool": "box",
            "allowed_tools": list(SUPPORTED_TOOL_KEYS),
        },
        project_classes=(),
    )


def _fields(task_uuid: str) -> dict[str, str]:
    return {
        "label": f"label_id_{task_uuid}",
        "comment": f"comment_{task_uuid}",
        "selected_features": f"selected_features_{task_uuid}",
        "geometry": f"feature_geometry_json_{task_uuid}",
        "annotation_policy_revision": f"annotation_policy_revision_{task_uuid}",
        "grade_revision": f"grade_revision_{task_uuid}",
    }


def _media(filename: str, laterality: str, view: str) -> WorkbenchMediaDTO:
    url = url_for("static", filename=f"grader-pwa/demo/{filename}")
    return WorkbenchMediaDTO(
        source_type="encounter_set_image",
        image_uuid=f"demo-{filename.rsplit('.', 1)[0]}",
        media_url=url,
        thumbnail_url=url,
        laterality=laterality,
        width=DEMO_IMAGE_SIZE,
        height=DEMO_IMAGE_SIZE,
        metadata={"view": view, "demo": True},
    )


def build_demo_workbench(db) -> WorkbenchDTO:
    now = utcnow()
    panels: list[WorkbenchPanelDTO] = []
    for scope_id, (image_disease_name, encounter_disease_name) in enumerate(DEMO_SCOPES, start=1):
        image_disease_id, image_grades = _grade_options(db, image_disease_name, scope_id * 100 + 1)
        encounter_disease_id, encounter_grades = _grade_options(db, encounter_disease_name, scope_id * 100 + 2)
        for position, laterality, filename, view in DEMO_IMAGES:
            task_uuid = f"demo-{scope_id}-image-{position}"
            panels.append(
                WorkbenchPanelDTO(
                    task_uuid=task_uuid,
                    disease_id=image_disease_id,
                    disease_name=image_disease_name,
                    target_level="image",
                    scope_id=scope_id,
                    image_position=position,
                    editable=True,
                    unavailable_reason=None,
                    media=_media(filename, laterality, view),
                    evidence=(),
                    grades=image_grades,
                    annotation=_annotation(),
                    existing_grade=None,
                    consensus=None,
                    draft_observation=None,
                    task_state="pending",
                    fields=_fields(task_uuid),
                )
            )
        task_uuid = f"demo-{scope_id}-encounter"
        panels.append(
            WorkbenchPanelDTO(
                task_uuid=task_uuid,
                disease_id=encounter_disease_id,
                disease_name=encounter_disease_name,
                target_level="encounter",
                scope_id=scope_id,
                image_position=None,
                editable=True,
                unavailable_reason=None,
                media=None,
                evidence=(),
                grades=encounter_grades,
                annotation=_annotation(),
                existing_grade=None,
                consensus=None,
                draft_observation=None,
                task_state="pending",
                fields=_fields(task_uuid),
            )
        )
    return WorkbenchDTO(
        lease=WorkbenchLeaseDTO(
            session_uuid=DEMO_SESSION_UUID,
            role_slot="resident",
            workflow="package",
            token_generation=0,
            acquired_at=now,
            idle_expires_at=now + timedelta(minutes=30),
            absolute_expires_at=now + timedelta(minutes=30),
        ),
        configuration_fingerprint="demo",
        source=WorkbenchSourceDTO(
            source_type="encounter_set_image",
            profile_id=None,
            profile_lineage="demo",
            project_id=None,
            lab_unit_id=0,
            profile={"name": "Demo encounter set"},
        ),
        panels=tuple(panels),
        allowed_actions=("save_close", "save_next"),
        workflow_config={
            "package_uuid": DEMO_SESSION_UUID,
            "package_name": "Demo encounter set",
            "package_state": "demo",
            "package_revision": 0,
            "policy_schema_version": 1,
            "policy_revision": NON_PROJECT_POLICY_REVISION,
            "demo": True,
        },
    )
