"""Service layer for grading scheme administration.

The database model is still named Disease. In the admin UI and API, one
Disease row is treated as one grading scheme/evaluation workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
import html
from html.parser import HTMLParser
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db_transaction_manager import get_db_session, transaction_scope
from models import (
    AIModelDisease,
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    GradingsFeatures,
    LinkedDiseaseGrading,
    Project,
    UserDiseaseUnitRole,
)
from upload_profiles.admin_service import MutationResult
from upload_profiles.models import (
    PatientEncounterTargetDisease,
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeImageGradingScheme,
)

VALID_SCOPES = frozenset({"image", "encounter"})
VALID_REMIDIO_OCR_LINKAGES = frozenset({"none", "dr", "amd", "glaucoma"})
CORE_SCHEME_IDS = frozenset({1, 2, 3})
GUIDELINE_ALLOWED_TAGS = frozenset({"strong", "b", "em", "i", "ul", "ol", "li", "br", "p"})
EXTERNAL_USAGE_KEYS = frozenset(
    {
        "tasks",
        "direct_uploads",
        "upload_profiles",
        "encounter_targets",
        "encounter_set_types",
        "eligibility_roles",
        "ai_models",
        "submitted_grades",
    }
)
STANDARD_NON_GRADABLE_REASONS = (
    "Poor focus",
    "Motion blur",
    "Poor exposure",
    "Artifact or obstruction",
    "Incomplete or wrong field",
    "Wrong eye or view",
    "Missing required image or view",
    "Image/document mismatch",
    "Other",
)


@dataclass(frozen=True)
class GradingSchemeInput:
    name: str
    grading_scope: str
    remidio_ocr_linkage: str = "none"
    parent_scheme_id: int | None = None


@dataclass(frozen=True)
class GradeFeatureInput:
    sr_no: int
    label: str


@dataclass(frozen=True)
class GradeInput:
    impression: str
    display_order: int
    is_active: bool
    prioritize_for_task_selection: bool
    is_ungradable: bool
    guidelines: str | None
    features: list[GradeFeatureInput]


def list_grading_schemes(*, include_usage: bool = True) -> list[dict[str, Any]]:
    """Return grading scheme summaries as detached-safe DTO dictionaries."""
    with get_db_session() as db:
        schemes = (
            db.execute(
                select(Disease)
                .options(
                    selectinload(Disease.disease_gradings).selectinload(DiseaseGrading.features)
                )
                .order_by(Disease.name.asc())
            )
            .scalars()
            .all()
        )
        usage_counts = _usage_counts(db) if include_usage else {}
        linkages = _linkage_maps(db, {scheme.id for scheme in schemes})
        upload_profile_maps = _upload_profile_maps(db, {scheme.id for scheme in schemes})
        summaries = [
            _scheme_summary(scheme, usage_counts.get(scheme.id, {}), linkages, upload_profile_maps)
            for scheme in schemes
        ]
        return _order_scheme_tree(summaries)


def get_grading_scheme(scheme_id: int) -> MutationResult:
    """Return one grading scheme detail DTO."""
    with get_db_session() as db:
        scheme = (
            db.execute(
                select(Disease)
                .options(
                    selectinload(Disease.disease_gradings).selectinload(DiseaseGrading.features)
                )
                .where(Disease.id == scheme_id)
            )
            .scalar_one_or_none()
        )
        if scheme is None:
            return MutationResult(False, "Grading scheme not found.", 404)
        usage = _usage_counts(db, scheme_ids={scheme.id}).get(scheme.id, {})
        linkages = _linkage_maps(db, {scheme.id})
        upload_profile_maps = _upload_profile_maps(db, {scheme.id})
        return MutationResult(
            True,
            "Grading scheme loaded.",
            payload={"grading_scheme": _scheme_detail(db, scheme, usage, linkages, upload_profile_maps)},
        )


def create_grading_scheme(scheme_input: GradingSchemeInput) -> MutationResult:
    """Create a grading scheme backed by a Disease row."""
    error = _validate_scheme_input(scheme_input)
    if error:
        return MutationResult(False, error, 400)

    try:
        with transaction_scope() as db:
            existing = db.execute(
                select(Disease.id).where(func.lower(Disease.name) == scheme_input.name.lower())
            ).scalar_one_or_none()
            if existing:
                return MutationResult(False, "A grading scheme with this name already exists.", 400)
            parent_error = _validate_parent_link(db, 0, scheme_input.parent_scheme_id, scheme_input.grading_scope)
            if parent_error:
                return MutationResult(False, parent_error, 400)
            scheme = Disease(
                name=scheme_input.name,
                grading_scope=scheme_input.grading_scope,
                remidio_ocr_linkage=_normalized_remidio_ocr_linkage(scheme_input),
            )
            db.add(scheme)
            db.flush()
            _set_parent_link(db, scheme.id, scheme_input.parent_scheme_id)
            return MutationResult(
                True,
                "Grading scheme created.",
                201,
                payload={"grading_scheme_id": scheme.id},
            )
    except IntegrityError:
        return MutationResult(False, "Duplicate or invalid grading scheme.", 400)


def update_grading_scheme(scheme_id: int, scheme_input: GradingSchemeInput) -> MutationResult:
    """Update grading scheme metadata."""
    error = _validate_scheme_input(scheme_input)
    if error:
        return MutationResult(False, error, 400)

    try:
        with transaction_scope() as db:
            scheme = db.get(Disease, scheme_id)
            if scheme is None:
                return MutationResult(False, "Grading scheme not found.", 404)

            existing = db.execute(
                select(Disease.id).where(
                    func.lower(Disease.name) == scheme_input.name.lower(),
                    Disease.id != scheme_id,
                )
            ).scalar_one_or_none()
            if existing:
                return MutationResult(False, "A grading scheme with this name already exists.", 400)

            if scheme_id in CORE_SCHEME_IDS and scheme.name.lower() != scheme_input.name.lower():
                return MutationResult(False, "Core grading schemes cannot be renamed.", 400)

            parent_error = _validate_parent_link(db, scheme_id, scheme_input.parent_scheme_id, scheme_input.grading_scope)
            if parent_error:
                return MutationResult(False, parent_error, 400)
            scope_error = _validate_linked_scope_change(
                db,
                scheme_id,
                scheme_input.grading_scope,
                scheme_input.parent_scheme_id,
            )
            if scope_error:
                return MutationResult(False, scope_error, 400)

            scheme.name = scheme_input.name
            scheme.grading_scope = scheme_input.grading_scope
            scheme.remidio_ocr_linkage = _normalized_remidio_ocr_linkage(scheme_input)
            _set_parent_link(db, scheme_id, scheme_input.parent_scheme_id)
            return MutationResult(True, "Grading scheme updated.", payload={"grading_scheme_id": scheme.id})
    except IntegrityError:
        return MutationResult(False, "Duplicate or invalid grading scheme.", 400)


def duplicate_grading_scheme(scheme_id: int) -> MutationResult:
    """Duplicate scheme metadata plus configured grades/features into an unused copy."""
    try:
        with transaction_scope() as db:
            source = (
                db.execute(
                    select(Disease)
                    .options(
                        selectinload(Disease.disease_gradings).selectinload(DiseaseGrading.features)
                    )
                    .where(Disease.id == scheme_id)
                )
                .scalar_one_or_none()
            )
            if source is None:
                return MutationResult(False, "Grading scheme not found.", 404)

            parent_id = db.execute(
                select(LinkedDiseaseGrading.primary_disease_id).where(
                    LinkedDiseaseGrading.linked_disease_id == scheme_id,
                    LinkedDiseaseGrading.is_active.is_(True),
                )
            ).scalar_one_or_none()
            name = _unique_copy_name(db, source.name)
            copy = Disease(
                name=name,
                grading_scope=source.grading_scope,
                remidio_ocr_linkage=source.remidio_ocr_linkage or "none",
            )
            db.add(copy)
            db.flush()

            _set_parent_link(db, copy.id, parent_id)
            for source_grade in sorted(source.disease_gradings or [], key=lambda item: (item.display_order, item.id)):
                grade_copy = DiseaseGrading(
                    disease_id=copy.id,
                    impression=source_grade.impression,
                    display_order=source_grade.display_order,
                    is_active=source_grade.is_active,
                    prioritize_for_task_selection=bool(source_grade.prioritize_for_task_selection),
                    is_ungradable=bool(source_grade.is_ungradable),
                    guidelines=_sanitize_guidelines_html(source_grade.guidelines),
                )
                db.add(grade_copy)
                db.flush()
                for feature in sorted(source_grade.features or [], key=lambda item: (item.sr_no, item.id)):
                    db.add(
                        GradingsFeatures(
                            disease_grading_id=grade_copy.id,
                            sr_no=feature.sr_no,
                            label=feature.label,
                        )
                    )

            return MutationResult(
                True,
                "Grading scheme duplicated.",
                201,
                payload={
                    "source_grading_scheme_id": scheme_id,
                    "grading_scheme_id": copy.id,
                    "grading_scheme_name": name,
                },
            )
    except IntegrityError:
        return MutationResult(False, "Duplicate or invalid grading scheme copy.", 400)


def delete_grading_scheme(scheme_id: int) -> MutationResult:
    """Delete an unused non-core grading scheme and its configured grades."""
    with transaction_scope() as db:
        scheme = db.get(Disease, scheme_id)
        if scheme is None:
            return MutationResult(False, "Grading scheme not found.", 404)
        if scheme_id in CORE_SCHEME_IDS:
            return MutationResult(False, "Core grading schemes cannot be deleted.", 400)

        usage = _usage_counts(db, scheme_ids={scheme_id}).get(scheme_id, _empty_usage())
        linkages = _linkage_maps(db, {scheme_id}).get(scheme_id, _empty_linkage())
        blockers = _delete_blockers(usage, linkages)
        if blockers:
            return MutationResult(
                False,
                "Grading scheme cannot be deleted because it is in use: " + ", ".join(blockers) + ".",
                400,
            )

        grade_ids = db.execute(select(DiseaseGrading.id).where(DiseaseGrading.disease_id == scheme_id)).scalars().all()
        if grade_ids:
            db.query(GradingsFeatures).filter(GradingsFeatures.disease_grading_id.in_(grade_ids)).delete(synchronize_session=False)
            db.query(DiseaseGrading).filter(DiseaseGrading.id.in_(grade_ids)).delete(synchronize_session=False)
        db.delete(scheme)
        return MutationResult(True, "Grading scheme deleted.", payload={"grading_scheme_id": scheme_id})


def create_grade(scheme_id: int, grade_input: GradeInput) -> MutationResult:
    """Create a grade and its selectable features for a scheme."""
    error = _validate_grade_input(grade_input)
    if error:
        return MutationResult(False, error, 400)
    try:
        with transaction_scope() as db:
            scheme = db.get(Disease, scheme_id)
            if scheme is None:
                return MutationResult(False, "Grading scheme not found.", 404)
            duplicate = db.execute(
                select(DiseaseGrading.id).where(
                    DiseaseGrading.disease_id == scheme_id,
                    func.lower(DiseaseGrading.impression) == grade_input.impression.lower(),
                )
            ).scalar_one_or_none()
            if duplicate:
                return MutationResult(False, "This grade already exists for the selected scheme.", 400)
            grade = DiseaseGrading(
                disease_id=scheme_id,
                impression=grade_input.impression,
                display_order=grade_input.display_order,
                is_active=grade_input.is_active,
                prioritize_for_task_selection=grade_input.prioritize_for_task_selection,
                is_ungradable=grade_input.is_ungradable,
                guidelines=_sanitize_guidelines_html(grade_input.guidelines),
            )
            db.add(grade)
            db.flush()
            _replace_features(db, grade.id, grade_input.features)
            db.flush()
            return MutationResult(True, "Grade created.", 201, payload={"grading_scheme_id": scheme_id, "grade_id": grade.id})
    except IntegrityError:
        return MutationResult(False, "Duplicate or invalid grade configuration.", 400)


def update_grade(scheme_id: int, grade_id: int, grade_input: GradeInput) -> MutationResult:
    """Update a grade and replace its features."""
    error = _validate_grade_input(grade_input)
    if error:
        return MutationResult(False, error, 400)
    try:
        with transaction_scope() as db:
            grade = db.get(DiseaseGrading, grade_id)
            if grade is None or grade.disease_id != scheme_id:
                return MutationResult(False, "Grade not found for this grading scheme.", 404)
            duplicate = db.execute(
                select(DiseaseGrading.id).where(
                    DiseaseGrading.disease_id == scheme_id,
                    DiseaseGrading.id != grade_id,
                    func.lower(DiseaseGrading.impression) == grade_input.impression.lower(),
                )
            ).scalar_one_or_none()
            if duplicate:
                return MutationResult(False, "This grade already exists for the selected scheme.", 400)
            grade.impression = grade_input.impression
            grade.display_order = grade_input.display_order
            grade.is_active = grade_input.is_active
            grade.prioritize_for_task_selection = grade_input.prioritize_for_task_selection
            grade.is_ungradable = grade_input.is_ungradable
            grade.guidelines = _sanitize_guidelines_html(grade_input.guidelines)
            db.query(GradingsFeatures).filter(GradingsFeatures.disease_grading_id == grade.id).delete(synchronize_session=False)
            _replace_features(db, grade.id, grade_input.features)
            db.flush()
            return MutationResult(True, "Grade updated.", payload={"grading_scheme_id": scheme_id, "grade_id": grade.id})
    except IntegrityError:
        return MutationResult(False, "Duplicate or invalid grade configuration.", 400)


def set_grade_active(scheme_id: int, grade_id: int, active: bool) -> MutationResult:
    """Activate or deactivate a grade without deleting historical labels."""
    with transaction_scope() as db:
        grade = db.get(DiseaseGrading, grade_id)
        if grade is None or grade.disease_id != scheme_id:
            return MutationResult(False, "Grade not found for this grading scheme.", 404)
        grade.is_active = active
        return MutationResult(True, "Grade activated." if active else "Grade deactivated.", payload={"grading_scheme_id": scheme_id, "grade_id": grade.id})


def _validate_scheme_input(scheme_input: GradingSchemeInput) -> str | None:
    if not scheme_input.name:
        return "Grading scheme name is required."
    if scheme_input.grading_scope not in VALID_SCOPES:
        return "Grading scheme scope must be image or encounter."
    if scheme_input.remidio_ocr_linkage not in VALID_REMIDIO_OCR_LINKAGES:
        return "Remidio OCR linkage must be none, DR, AMD, or glaucoma."
    return None


def _normalized_remidio_ocr_linkage(scheme_input: GradingSchemeInput) -> str:
    if scheme_input.grading_scope != "image":
        return "none"
    return scheme_input.remidio_ocr_linkage


def _unique_copy_name(db, source_name: str) -> str:
    base_name = f"Copy of {source_name}".strip()
    candidate = base_name[:255]
    suffix = 2
    while db.execute(select(Disease.id).where(func.lower(Disease.name) == candidate.lower())).scalar_one_or_none():
        suffix_text = f" ({suffix})"
        candidate = f"{base_name[:255 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _validate_parent_link(db, scheme_id: int, parent_scheme_id: int | None, scope: str) -> str | None:
    if parent_scheme_id is None:
        return None
    if parent_scheme_id == scheme_id:
        return "A grading scheme cannot be its own parent."
    parent = db.get(Disease, parent_scheme_id)
    if parent is None:
        return "Selected parent grading scheme was not found."
    if parent.grading_scope != scope:
        return "Parent and child grading schemes must have the same scope."
    if parent_scheme_id in _descendant_ids(db, scheme_id):
        return "Selected parent would create a linked-scheme cycle."
    return None


def _validate_linked_scope_change(db, scheme_id: int, scope: str, parent_scheme_id: int | None) -> str | None:
    linked_ids = set()
    active_links = db.execute(
        select(LinkedDiseaseGrading.primary_disease_id, LinkedDiseaseGrading.linked_disease_id).where(
            LinkedDiseaseGrading.is_active.is_(True),
            (LinkedDiseaseGrading.primary_disease_id == scheme_id)
            | (LinkedDiseaseGrading.linked_disease_id == scheme_id),
        )
    ).all()
    for primary_id, linked_id in active_links:
        if linked_id == scheme_id:
            if parent_scheme_id is not None:
                linked_ids.add(parent_scheme_id)
            continue
        linked_ids.add(linked_id)
    if not linked_ids:
        return None
    mismatched = db.execute(
        select(Disease.name).where(Disease.id.in_(linked_ids), Disease.grading_scope != scope)
    ).scalars().all()
    if mismatched:
        return "Linked parent and child grading schemes must keep the same scope."
    return None


def _set_parent_link(db, scheme_id: int, parent_scheme_id: int | None) -> None:
    existing = db.execute(
        select(LinkedDiseaseGrading).where(LinkedDiseaseGrading.linked_disease_id == scheme_id)
    ).scalar_one_or_none()
    if parent_scheme_id is None:
        if existing:
            existing.is_active = False
        return

    if existing:
        parent_changed = existing.primary_disease_id != parent_scheme_id
        existing.primary_disease_id = parent_scheme_id
        existing.is_active = True
        if parent_changed or existing.display_order <= 0:
            existing.display_order = _next_link_display_order(db, parent_scheme_id)
        return

    db.add(
        LinkedDiseaseGrading(
            primary_disease_id=parent_scheme_id,
            linked_disease_id=scheme_id,
            display_order=_next_link_display_order(db, parent_scheme_id),
            is_active=True,
        )
    )


def _next_link_display_order(db, parent_scheme_id: int) -> int:
    max_order = db.execute(
        select(func.max(LinkedDiseaseGrading.display_order)).where(
            LinkedDiseaseGrading.primary_disease_id == parent_scheme_id,
            LinkedDiseaseGrading.is_active.is_(True),
        )
    ).scalar_one_or_none()
    return int(max_order or 0) + 1


def _descendant_ids(db, scheme_id: int) -> set[int]:
    rows = db.execute(
        select(LinkedDiseaseGrading.primary_disease_id, LinkedDiseaseGrading.linked_disease_id).where(
            LinkedDiseaseGrading.is_active.is_(True)
        )
    ).all()
    children_by_parent: dict[int, list[int]] = {}
    for primary_id, linked_id in rows:
        children_by_parent.setdefault(primary_id, []).append(linked_id)
    descendants: set[int] = set()
    stack = list(children_by_parent.get(scheme_id, []))
    while stack:
        child_id = stack.pop()
        if child_id in descendants:
            continue
        descendants.add(child_id)
        stack.extend(children_by_parent.get(child_id, []))
    return descendants


def _validate_grade_input(grade_input: GradeInput) -> str | None:
    if not grade_input.impression:
        return "Grade label is required."
    labels = [feature.label.lower() for feature in grade_input.features if feature.label]
    if len(labels) != len(set(labels)):
        return "Duplicate feature labels are not allowed."
    return None


def _replace_features(db, grade_id: int, features: list[GradeFeatureInput]) -> None:
    for index, feature_input in enumerate(features, start=1):
        label = feature_input.label.strip()
        if not label:
            continue
        sr_no = feature_input.sr_no if feature_input.sr_no > 0 else index
        db.add(GradingsFeatures(disease_grading_id=grade_id, sr_no=sr_no, label=label))


class _GuidelinesSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in GUIDELINE_ALLOWED_TAGS:
            self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in GUIDELINE_ALLOWED_TAGS and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def sanitized(self) -> str:
        return "".join(self.parts)


def _sanitize_guidelines_html(value: str | None) -> str | None:
    if not value:
        return None
    parser = _GuidelinesSanitizer()
    parser.feed(value)
    parser.close()
    cleaned = parser.sanitized().strip()
    return cleaned or None


def _scheme_summary(
    scheme: Disease,
    usage: dict[str, int],
    linkages: dict[int, dict[str, Any]] | None = None,
    upload_profile_maps: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    grades = list(scheme.disease_gradings or [])
    active_grades = [grade for grade in grades if grade.is_active]
    prioritized_grades = [grade for grade in grades if grade.prioritize_for_task_selection]
    ungradable_grades = [grade for grade in grades if grade.is_ungradable]
    feature_count = sum(len(grade.features or []) for grade in grades)
    linkage = (linkages or {}).get(scheme.id, _empty_linkage())
    associated_upload_profiles = (upload_profile_maps or {}).get(scheme.id, [])
    return {
        "id": scheme.id,
        "name": scheme.name,
        "grading_scope": scheme.grading_scope,
        "remidio_ocr_linkage": scheme.remidio_ocr_linkage or "none",
        "grade_count": len(grades),
        "active_grade_count": len(active_grades),
        "prioritized_grade_count": len(prioritized_grades),
        "ungradable_grade_count": len(ungradable_grades),
        "feature_count": feature_count,
        "is_core": scheme.id in CORE_SCHEME_IDS,
        "linkage": linkage,
        "is_linked_child": linkage["parent"] is not None,
        "linked_child_count": len(linkage["children"]),
        "can_delete": scheme.id not in CORE_SCHEME_IDS
        and _external_usage_total(usage) == 0
        and linkage["parent"] is None
        and not linkage["children"],
        "usage": usage,
        "usage_total": _external_usage_total(usage),
        "associated_upload_profiles": associated_upload_profiles,
    }


def _scheme_detail(
    db,
    scheme: Disease,
    usage: dict[str, int],
    linkages: dict[int, dict[str, Any]] | None = None,
    upload_profile_maps: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    summary = _scheme_summary(scheme, usage, linkages, upload_profile_maps)
    grades = list(scheme.disease_gradings or [])
    summary["grades"] = [
        {
            "id": grade.id,
            "impression": grade.impression,
            "display_order": grade.display_order,
            "is_active": grade.is_active,
            "prioritize_for_task_selection": bool(grade.prioritize_for_task_selection),
            "is_ungradable": bool(grade.is_ungradable),
            "guidelines": _sanitize_guidelines_html(grade.guidelines),
            "features": [
                {
                    "id": feature.id,
                    "sr_no": feature.sr_no,
                    "label": feature.label,
                }
                for feature in sorted(grade.features or [], key=lambda item: (item.sr_no, item.id))
            ],
        }
        for grade in sorted(grades, key=lambda item: (item.display_order, item.id))
    ]
    summary["non_gradable_reasons"] = list(STANDARD_NON_GRADABLE_REASONS)
    summary["parent_candidates"] = _parent_candidates(db, scheme.id, scheme.grading_scope, linkages or {})
    return summary


def _parent_candidates(db, scheme_id: int, scope: str, linkages: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    descendant_ids = _descendant_ids(db, scheme_id)
    rows = db.execute(
        select(Disease.id, Disease.name, Disease.grading_scope)
        .where(
            Disease.id != scheme_id,
            Disease.grading_scope == scope,
        )
        .order_by(Disease.name)
    ).all()
    current_parent_id = ((linkages.get(scheme_id) or {}).get("parent") or {}).get("id")
    candidates = []
    for row_id, name, grading_scope in rows:
        if row_id in descendant_ids:
            continue
        candidates.append(
            {
                "id": row_id,
                "name": name,
                "grading_scope": grading_scope,
                "selected": row_id == current_parent_id,
            }
        )
    return candidates


def _linkage_maps(db, scheme_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not scheme_ids:
        return {}

    rows = db.execute(
        select(
            LinkedDiseaseGrading.primary_disease_id,
            LinkedDiseaseGrading.linked_disease_id,
            LinkedDiseaseGrading.display_order,
            Disease.name.label("linked_name"),
        )
        .join(Disease, Disease.id == LinkedDiseaseGrading.linked_disease_id)
        .where(
            LinkedDiseaseGrading.is_active.is_(True),
            LinkedDiseaseGrading.primary_disease_id.in_(scheme_ids),
        )
        .order_by(LinkedDiseaseGrading.display_order, Disease.name)
    ).all()
    parent_rows = db.execute(
        select(
            LinkedDiseaseGrading.primary_disease_id,
            LinkedDiseaseGrading.linked_disease_id,
            LinkedDiseaseGrading.display_order,
            Disease.name.label("primary_name"),
        )
        .join(Disease, Disease.id == LinkedDiseaseGrading.primary_disease_id)
        .where(
            LinkedDiseaseGrading.is_active.is_(True),
            LinkedDiseaseGrading.linked_disease_id.in_(scheme_ids),
        )
    ).all()

    linkages = {scheme_id: _empty_linkage() for scheme_id in scheme_ids}
    for primary_id, linked_id, display_order, linked_name in rows:
        linkages.setdefault(primary_id, _empty_linkage())["children"].append(
            {
                "id": linked_id,
                "name": linked_name,
                "display_order": display_order,
            }
        )
    for primary_id, linked_id, display_order, primary_name in parent_rows:
        linkages.setdefault(linked_id, _empty_linkage())["parent"] = {
            "id": primary_id,
            "name": primary_name,
            "display_order": display_order,
        }
    return linkages


def _empty_linkage() -> dict[str, Any]:
    return {"parent": None, "children": []}


def _upload_profile_maps(db, scheme_ids: set[int]) -> dict[int, list[dict[str, Any]]]:
    if not scheme_ids:
        return {}
    profiles_by_scheme = {scheme_id: [] for scheme_id in scheme_ids}
    seen: set[tuple[int, int]] = set()

    rows = db.execute(
        select(
            UploadProfileDisease.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfile.active,
            func.coalesce(func.string_agg(Project.title, ", "), "Unmapped").label("project_title"),
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileDisease.upload_profile_id)
        .outerjoin(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .outerjoin(Project, Project.id == ProjectUploadProfile.project_id)
        .where(UploadProfileDisease.disease_id.in_(scheme_ids))
        .group_by(UploadProfileDisease.disease_id, UploadProfile.id, UploadProfile.name, UploadProfile.active)
        .order_by(UploadProfile.active.desc(), UploadProfile.name)
    ).all()
    for scheme_id, profile_id, profile_name, active, project_title in rows:
        seen.add((scheme_id, profile_id))
        profiles_by_scheme.setdefault(scheme_id, []).append(
            {
                "id": profile_id,
                "name": profile_name,
                "active": bool(active),
                "project_title": project_title,
            }
        )
    encounter_rows = db.execute(
        select(
            UploadProfileEncounterSetType.encounter_grading_scheme_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfile.active,
            func.coalesce(func.string_agg(Project.title, ", "), "Unmapped").label("project_title"),
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileEncounterSetType.upload_profile_id)
        .outerjoin(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .outerjoin(Project, Project.id == ProjectUploadProfile.project_id)
        .where(
            UploadProfileEncounterSetType.encounter_grading_scheme_id.in_(scheme_ids),
            UploadProfileEncounterSetType.active.is_(True),
        )
        .group_by(
            UploadProfileEncounterSetType.encounter_grading_scheme_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfile.active,
        )
        .order_by(UploadProfile.active.desc(), UploadProfile.name)
    ).all()
    for scheme_id, profile_id, profile_name, active, project_title in encounter_rows:
        if (scheme_id, profile_id) in seen:
            continue
        seen.add((scheme_id, profile_id))
        profiles_by_scheme.setdefault(scheme_id, []).append(
            {
                "id": profile_id,
                "name": profile_name,
                "active": bool(active),
                "project_title": project_title,
            }
        )
    image_rows = db.execute(
        select(
            UploadProfileEncounterSetTypeImageGradingScheme.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfile.active,
            func.coalesce(func.string_agg(Project.title, ", "), "Unmapped").label("project_title"),
        )
        .join(
            UploadProfileEncounterSetType,
            UploadProfileEncounterSetType.id == UploadProfileEncounterSetTypeImageGradingScheme.upload_profile_encounter_set_type_id,
        )
        .join(UploadProfile, UploadProfile.id == UploadProfileEncounterSetType.upload_profile_id)
        .outerjoin(ProjectUploadProfile, ProjectUploadProfile.upload_profile_id == UploadProfile.id)
        .outerjoin(Project, Project.id == ProjectUploadProfile.project_id)
        .where(
            UploadProfileEncounterSetTypeImageGradingScheme.disease_id.in_(scheme_ids),
            UploadProfileEncounterSetTypeImageGradingScheme.active.is_(True),
            UploadProfileEncounterSetType.active.is_(True),
        )
        .group_by(
            UploadProfileEncounterSetTypeImageGradingScheme.disease_id,
            UploadProfile.id,
            UploadProfile.name,
            UploadProfile.active,
        )
        .order_by(UploadProfile.active.desc(), UploadProfile.name)
    ).all()
    for scheme_id, profile_id, profile_name, active, project_title in image_rows:
        if (scheme_id, profile_id) in seen:
            continue
        profiles_by_scheme.setdefault(scheme_id, []).append(
            {
                "id": profile_id,
                "name": profile_name,
                "active": bool(active),
                "project_title": project_title,
            }
        )
    return profiles_by_scheme


def _external_usage_total(usage: dict[str, int]) -> int:
    return sum(usage.get(key, 0) for key in EXTERNAL_USAGE_KEYS)


def _delete_blockers(usage: dict[str, int], linkage: dict[str, Any]) -> list[str]:
    labels = {
        "tasks": "tasks",
        "direct_uploads": "direct uploads",
        "upload_profiles": "upload profiles",
        "encounter_targets": "encounter targets",
        "encounter_set_types": "EncounterSetTypes",
        "eligibility_roles": "eligibility roles",
        "ai_models": "AI models",
        "submitted_grades": "submitted grades",
    }
    blockers = [label for key, label in labels.items() if usage.get(key, 0) > 0]
    if linkage["parent"]:
        blockers.append("linked parent relationship")
    if linkage["children"]:
        blockers.append("linked child relationships")
    return blockers


def _order_scheme_tree(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order linked schemes as parent followed immediately by children."""
    by_id = {row["id"]: row for row in rows}
    children_by_parent: dict[int, list[dict[str, Any]]] = {row["id"]: [] for row in rows}
    for row in rows:
        parent = row["linkage"]["parent"]
        if parent and parent["id"] in by_id:
            children_by_parent.setdefault(parent["id"], []).append(row)

    for children in children_by_parent.values():
        children.sort(key=lambda row: (row["linkage"]["parent"]["display_order"], row["name"].lower(), row["id"]))

    roots = [
        row
        for row in rows
        if not row["linkage"]["parent"] or row["linkage"]["parent"]["id"] not in by_id
    ]
    roots.sort(key=lambda row: (row["name"].lower(), row["id"]))

    ordered: list[dict[str, Any]] = []
    visited: set[int] = set()

    def append_branch(row: dict[str, Any], depth: int) -> None:
        if row["id"] in visited:
            return
        visited.add(row["id"])
        row["tree_depth"] = depth
        ordered.append(row)
        for child in children_by_parent.get(row["id"], []):
            append_branch(child, depth + 1)

    for root in roots:
        append_branch(root, 0)
    for row in sorted(rows, key=lambda item: (item["name"].lower(), item["id"])):
        append_branch(row, 0)
    return ordered


def _usage_counts(db, *, scheme_ids: set[int] | None = None) -> dict[int, dict[str, int]]:
    filters = []
    if scheme_ids:
        filters.append(Disease.id.in_(scheme_ids))

    scheme_id_rows = db.execute(select(Disease.id).where(*filters)).scalars().all()
    ids = set(scheme_id_rows)
    usage = {scheme_id: _empty_usage() for scheme_id in ids}
    if not ids:
        return usage

    _merge_count(
        usage,
        db.execute(
            select(GradingTask.disease_id, func.count(GradingTask.id))
            .where(GradingTask.disease_id.in_(ids))
            .group_by(GradingTask.disease_id)
        ).all(),
        "tasks",
    )
    _merge_count(
        usage,
        db.execute(
            select(DirectImageUpload.disease_id, func.count(DirectImageUpload.id))
            .where(DirectImageUpload.disease_id.in_(ids))
            .group_by(DirectImageUpload.disease_id)
        ).all(),
        "direct_uploads",
    )
    _merge_count(
        usage,
        db.execute(
            select(UploadProfileDisease.disease_id, func.count(UploadProfileDisease.id))
            .where(UploadProfileDisease.disease_id.in_(ids))
            .group_by(UploadProfileDisease.disease_id)
        ).all(),
        "upload_profiles",
    )
    _merge_count(
        usage,
        db.execute(
            select(PatientEncounterTargetDisease.disease_id, func.count(PatientEncounterTargetDisease.id))
            .where(PatientEncounterTargetDisease.disease_id.in_(ids))
            .group_by(PatientEncounterTargetDisease.disease_id)
        ).all(),
        "encounter_targets",
    )
    _merge_count(
        usage,
        db.execute(
            select(UploadProfileEncounterSetType.encounter_grading_scheme_id, func.count(UploadProfileEncounterSetType.id))
            .where(
                UploadProfileEncounterSetType.encounter_grading_scheme_id.in_(ids),
                UploadProfileEncounterSetType.active.is_(True),
            )
            .group_by(UploadProfileEncounterSetType.encounter_grading_scheme_id)
        ).all(),
        "encounter_set_types",
    )
    _merge_count(
        usage,
        db.execute(
            select(
                UploadProfileEncounterSetTypeImageGradingScheme.disease_id,
                func.count(UploadProfileEncounterSetTypeImageGradingScheme.id),
            )
            .join(
                UploadProfileEncounterSetType,
                UploadProfileEncounterSetType.id == UploadProfileEncounterSetTypeImageGradingScheme.upload_profile_encounter_set_type_id,
            )
            .where(
                UploadProfileEncounterSetTypeImageGradingScheme.disease_id.in_(ids),
                UploadProfileEncounterSetTypeImageGradingScheme.active.is_(True),
                UploadProfileEncounterSetType.active.is_(True),
            )
            .group_by(UploadProfileEncounterSetTypeImageGradingScheme.disease_id)
        ).all(),
        "encounter_set_types",
    )
    _merge_count(
        usage,
        db.execute(
            select(UserDiseaseUnitRole.disease_id, func.count(UserDiseaseUnitRole.id))
            .where(UserDiseaseUnitRole.disease_id.in_(ids))
            .group_by(UserDiseaseUnitRole.disease_id)
        ).all(),
        "eligibility_roles",
    )
    _merge_count(
        usage,
        db.execute(
            select(AIModelDisease.disease_id, func.count(AIModelDisease.id))
            .where(AIModelDisease.disease_id.in_(ids))
            .group_by(AIModelDisease.disease_id)
        ).all(),
        "ai_models",
    )
    grade_subquery = select(DiseaseGrading.id, DiseaseGrading.disease_id).where(DiseaseGrading.disease_id.in_(ids)).subquery()
    _merge_count(
        usage,
        db.execute(
            select(grade_subquery.c.disease_id, func.count(Grade.id))
            .join(Grade, Grade.disease_grading_id == grade_subquery.c.id)
            .group_by(grade_subquery.c.disease_id)
        ).all(),
        "submitted_grades",
    )
    _merge_count(
        usage,
        db.execute(
            select(DiseaseGrading.disease_id, func.count(GradingsFeatures.id))
            .join(GradingsFeatures, GradingsFeatures.disease_grading_id == DiseaseGrading.id)
            .where(DiseaseGrading.disease_id.in_(ids))
            .group_by(DiseaseGrading.disease_id)
        ).all(),
        "features",
    )
    return usage


def _empty_usage() -> dict[str, int]:
    return {
        "tasks": 0,
        "direct_uploads": 0,
        "upload_profiles": 0,
        "encounter_targets": 0,
        "encounter_set_types": 0,
        "eligibility_roles": 0,
        "ai_models": 0,
        "submitted_grades": 0,
        "features": 0,
    }


def _merge_count(usage: dict[int, dict[str, int]], rows, key: str) -> None:
    for scheme_id, count in rows:
        if scheme_id in usage:
            usage[scheme_id][key] += int(count or 0)
