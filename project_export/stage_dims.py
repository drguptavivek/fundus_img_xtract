"""lookup stage: small dimension tables so ids and labels in the fact tables can be resolved offline."""
from __future__ import annotations

from sqlalchemy import select

from models import AIModel, Disease, DiseaseGrading, Hospital, LabUnit

from .tables import BuildContext


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    db = ctx.db
    labs = db.execute(
        select(LabUnit.id, LabUnit.name, LabUnit.hospital_id, Hospital.name)
        .join(Hospital, Hospital.id == LabUnit.hospital_id)
        .where(LabUnit.id.in_(list(ctx.scope.lab_unit_ids)))
        .order_by(LabUnit.id)
    ).all()
    labels = db.execute(
        select(Disease.name, DiseaseGrading.impression, DiseaseGrading.display_order, DiseaseGrading.is_active,
               DiseaseGrading.is_ungradable, DiseaseGrading.guidelines)
        .join(Disease, Disease.id == DiseaseGrading.disease_id)
        .order_by(Disease.name, DiseaseGrading.display_order)
    ).all()
    models = db.execute(select(AIModel.name, AIModel.version, AIModel.description).order_by(AIModel.id)).all()
    return {
        "dim_lab_units": [
            {"lab_unit_id": a, "lab_unit_name": b, "hospital_id": c, "hospital_name": d} for a, b, c, d in labs
        ],
        "dim_grade_labels": [
            {"disease": a, "grade_name": b, "display_order": c, "is_active": d, "is_ungradable": e, "guidelines": f}
            for a, b, c, d, e, f in labels
        ],
        "dim_ai_models": [{"ai_model": a, "ai_model_version": b, "description": c} for a, b, c in models],
    }
