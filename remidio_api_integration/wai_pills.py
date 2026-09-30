"""WAI (Wadhwani AI / MadhuNetrAI) automated-inference pills for the EncounterSet browser.

Only ``Grade.role_slot == 'ai'`` rows are read. Those are written exclusively by the
two WAI pipelines - ``remote_inference/dr_dme_service.py`` (DR + DME, per image) and
``services/wadhwani_glaucoma_inference.py`` (Glaucoma, per image) - never by the
separate Remidio OCR/PDF report sync (which writes DiabeticRetinopathyReport/AMDReport/
GlaucomaReport directly, with no Grade row). Do not widen this to include those reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from models import AIModel, Disease, DiseaseGrading, EncounterSetImage, Grade, GradingTask

WAI_KINDS = ("dr", "dme", "glaucoma")
WAI_PILL_LABELS = {"dr": "MN-DR", "dme": "MN-DME", "glaucoma": "RPC-Glau"}

# A WAI result is "positive" (refer advice) when the local grade it mapped to is in
# this set. Kept next to the labels so the rule is one reviewable place; compared
# case-insensitively against DiseaseGrading.impression.
WAI_POSITIVE_IMPRESSIONS = {
    "dr": frozenset({"mild dr", "moderate npdr", "severe npdr", "pdr"}),
    "dme": frozenset({"m1 referable diabetic maculopathy", "dme present"}),
    "glaucoma": frozenset({"suspect", "glaucoma"}),
}

# Severity order used to pick the "highest detected grade" for an image or encounter.
# Anything absent (Other Retinal, Not Gradable, unmapped) ranks below every listed grade.
WAI_GRADE_SEVERITY = {
    "dr": ("no dr", "mild dr", "moderate npdr", "severe npdr", "pdr"),
    "dme": ("m0 no dme", "dme present", "m1 referable diabetic maculopathy"),
    "glaucoma": ("normal", "suspect", "refer", "glaucoma"),
}

# The RPC glaucoma model only says referrable / not; the pipeline stores that as the
# local grade "Glaucoma" / "Normal". Show what the model actually says: Refer.
WAI_GRADE_DISPLAY = {"glaucoma": {"glaucoma": "Refer"}}


def display_grade(kind: str, impression: str | None) -> str | None:
    if not impression:
        return impression
    return WAI_GRADE_DISPLAY.get(kind, {}).get(impression.strip().casefold(), impression)


def status_label(kind: str, grades: Iterable[str | None]) -> str:
    """Header-pill text as one string, e.g. "MN-DR+ · Moderate NPDR".

    Used by the mobile field API so it reads exactly like the browse page: the pill
    label (with "+" when any grade refers), then the highest displayed grade.
    """
    raw = [grade for grade in grades if grade]
    positive = any(is_positive_impression(kind, grade) for grade in raw)
    label = WAI_PILL_LABELS[kind] + ("+" if positive else "")
    shown = [display_grade(kind, grade) for grade in raw]
    best = max(shown, key=lambda grade: grade_rank(kind, grade), default=None)
    return f"{label} · {best}" if best else label


def grade_rank(kind: str, grade: str | None) -> int:
    order = WAI_GRADE_SEVERITY.get(kind, ())
    key = (grade or "").strip().casefold()
    return order.index(key) if key in order else -1


@dataclass(frozen=True)
class WaiResult:
    model_label: str
    positive: bool
    grade: str | None = None  # exact local grade the model's output mapped to


def wai_disease_kind(disease: Disease) -> str | None:
    linkage = (disease.remidio_ocr_linkage or "none").lower()
    name = disease.name.strip().lower()
    # remidio_ocr_linkage is the primary signal, but fall back to an exact name match -
    # mirrors _positive_disease_list_matches' own resilience for a disease whose
    # linkage isn't configured (e.g. the seeded 'DR'/'Glaucoma' rows in test-db, which
    # default remidio_ocr_linkage to 'none').
    if linkage == "dr" or name == "dr":
        return "dr"
    if linkage == "glaucoma" or name == "glaucoma":
        return "glaucoma"
    if name == "dme":
        return "dme"
    return None


def is_positive_impression(kind: str, impression: str | None) -> bool:
    return (impression or "").strip().casefold() in WAI_POSITIVE_IMPRESSIONS.get(kind, frozenset())


def wai_results_by_encounter(
    db: Session, encounter_ids: Iterable[int]
) -> dict[int, dict[int, dict[str, WaiResult]]]:
    """encounter_id -> encounter_set_image_id -> kind ('dr'/'dme'/'glaucoma') -> result.

    One batched query for any number of encounters (the left rail lists up to 300).
    Grade.ai_model_id (not the denormalized ai_model_name/ai_model_version columns,
    which the Glaucoma pipeline leaves null) is the one field both pipelines populate,
    so it names the model regardless of which pipeline produced the grade. If an image
    has several AI grades for a kind, it is positive when any of them is.
    """
    ids = list(encounter_ids)
    if not ids:
        return {}
    rows = (
        db.query(
            EncounterSetImage.patient_encounter_id,
            GradingTask.encounter_set_image_id,
            Disease,
            AIModel,
            DiseaseGrading.impression,
        )
        .select_from(Grade)
        .join(GradingTask, GradingTask.id == Grade.task_id)
        .join(Disease, Disease.id == GradingTask.disease_id)
        .join(EncounterSetImage, EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .outerjoin(AIModel, AIModel.id == Grade.ai_model_id)
        .outerjoin(DiseaseGrading, DiseaseGrading.id == Grade.disease_grading_id)
        .filter(EncounterSetImage.patient_encounter_id.in_(ids), Grade.role_slot == "ai")
        .distinct()
        .all()
    )
    out: dict[int, dict[int, dict[str, WaiResult]]] = {}
    for encounter_id, image_id, disease, ai_model, impression in rows:
        kind = wai_disease_kind(disease)
        if kind is None or image_id is None:
            continue
        label = f"{ai_model.name} v{ai_model.version}" if ai_model else "Unknown model"
        positive = is_positive_impression(kind, impression)
        by_kind = out.setdefault(encounter_id, {}).setdefault(image_id, {})
        previous = by_kind.get(kind)
        grade = display_grade(kind, impression)
        if previous and grade_rank(kind, previous.grade) >= grade_rank(kind, grade):
            continue  # keep the highest grade if an image has several AI grades
        by_kind[kind] = WaiResult(label, positive, grade)
    return out


def image_pills(results: dict[str, WaiResult]) -> list[dict[str, object]]:
    return [_pill(kind, result.model_label, result.positive, result.grade) for kind, result in _ordered(results)]


def encounter_pills(images: dict[int, dict[str, WaiResult]]) -> list[dict[str, object]]:
    """One pill per kind across an encounter's images, carrying the highest detected grade."""
    models: dict[str, set[str]] = {}
    best: dict[str, WaiResult] = {}
    positive: dict[str, bool] = {}
    for results in images.values():
        for kind, result in results.items():
            models.setdefault(kind, set()).add(result.model_label)
            positive[kind] = positive.get(kind, False) or result.positive
            current = best.get(kind)
            if current is None or grade_rank(kind, result.grade) > grade_rank(kind, current.grade):
                best[kind] = result
    return [
        _pill(kind, ", ".join(sorted(models[kind])), positive[kind], best[kind].grade)
        for kind in WAI_KINDS
        if kind in models
    ]


def _ordered(results: dict[str, WaiResult]):
    return [(kind, results[kind]) for kind in WAI_KINDS if kind in results]


def _pill(kind: str, model_label: str, positive: bool, grade: str | None = None) -> dict[str, object]:
    title = f"{model_label} - refer advised" if positive else model_label
    if grade:
        title = f"{grade} ({title})"
    return {
        "label": WAI_PILL_LABELS[kind] + ("+" if positive else ""),
        "title": title,
        "positive": positive,
        "kind_label": WAI_PILL_LABELS[kind],
        "grade": grade,
    }
