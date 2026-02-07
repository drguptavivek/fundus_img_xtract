from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from flask import render_template
from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import Disease, GradingTask, LabUnit, LinkedDiseaseGrading


@roles_required("admin")
def linked_task_inconsistencies():
    """
    Admin view to surface primary/linked grading state mismatches.

    Targets:
      - primary resident_done + linked pending
      - primary resident2_done/final + linked resident_done
    """
    with transaction_scope() as db:
        PrimaryTask = aliased(GradingTask)
        LinkedTask = aliased(GradingTask)
        PrimaryDisease = aliased(Disease)
        LinkedDisease = aliased(Disease)

        image_match = or_(
            and_(
                PrimaryTask.encounter_file_id.isnot(None),
                PrimaryTask.encounter_file_id == LinkedTask.encounter_file_id,
            ),
            and_(
                PrimaryTask.direct_image_upload_id.isnot(None),
                PrimaryTask.direct_image_upload_id == LinkedTask.direct_image_upload_id,
            ),
            and_(
                PrimaryTask.patient_encounter_id.isnot(None),
                PrimaryTask.patient_encounter_id == LinkedTask.patient_encounter_id,
            ),
        )

        mismatch_filter = or_(
            and_(PrimaryTask.state == "resident_done", LinkedTask.state == "pending"),
            and_(
                PrimaryTask.state.in_(["resident2_done", "final"]),
                LinkedTask.state == "resident_done",
            ),
        )

        rows: Sequence[Any] = (
            db.query(
                PrimaryTask.id.label("primary_task_id"),
                PrimaryTask.state.label("primary_state"),
                PrimaryTask.encounter_file_id.label("primary_encounter_file_id"),
                PrimaryTask.direct_image_upload_id.label("primary_direct_image_upload_id"),
                PrimaryTask.patient_encounter_id.label("primary_patient_encounter_id"),
                LinkedTask.id.label("linked_task_id"),
                LinkedTask.state.label("linked_state"),
                LinkedTask.encounter_file_id.label("linked_encounter_file_id"),
                LinkedTask.direct_image_upload_id.label("linked_direct_image_upload_id"),
                LinkedTask.patient_encounter_id.label("linked_patient_encounter_id"),
                PrimaryDisease.name.label("primary_disease_name"),
                LinkedDisease.name.label("linked_disease_name"),
                LabUnit.name.label("lab_unit_name"),
                LabUnit.id.label("lab_unit_id"),
            )
            .join(LinkedTask, image_match)
            .join(
                LinkedDiseaseGrading,
                and_(
                    LinkedDiseaseGrading.primary_disease_id == PrimaryTask.disease_id,
                    LinkedDiseaseGrading.linked_disease_id == LinkedTask.disease_id,
                    LinkedDiseaseGrading.is_active.is_(True),
                ),
            )
            .join(PrimaryDisease, PrimaryDisease.id == PrimaryTask.disease_id)
            .join(LinkedDisease, LinkedDisease.id == LinkedTask.disease_id)
            .join(LabUnit, LabUnit.id == PrimaryTask.lab_unit_id)
            .filter(mismatch_filter)
            .order_by(PrimaryDisease.name, PrimaryTask.id.desc())
            .all()
        )

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        summary: Dict[Tuple[str, str], Dict[str, int]] = {}
        for row in rows:
            if row.primary_state == "resident_done" and row.linked_state == "pending":
                mismatch_key = "primary_resident_done_linked_pending"
            elif row.primary_state == "resident2_done" and row.linked_state == "resident_done":
                mismatch_key = "primary_resident2_done_linked_resident_done"
            elif row.primary_state == "final" and row.linked_state == "resident_done":
                mismatch_key = "primary_final_linked_resident_done"
            else:
                mismatch_key = "other"

            summary_key = (row.primary_disease_name, row.linked_disease_name)
            if summary_key not in summary:
                summary[summary_key] = {
                    "primary_final_linked_resident_done": 0,
                    "primary_resident2_done_linked_resident_done": 0,
                    "primary_resident_done_linked_pending": 0,
                    "other": 0,
                }
            summary[summary_key][mismatch_key] += 1

            grouped.setdefault(row.primary_disease_name, []).append(
                {
                    "primary_task_id": row.primary_task_id,
                    "primary_state": row.primary_state,
                    "primary_encounter_file_id": row.primary_encounter_file_id,
                    "primary_direct_image_upload_id": row.primary_direct_image_upload_id,
                    "primary_patient_encounter_id": row.primary_patient_encounter_id,
                    "linked_task_id": row.linked_task_id,
                    "linked_state": row.linked_state,
                    "linked_encounter_file_id": row.linked_encounter_file_id,
                    "linked_direct_image_upload_id": row.linked_direct_image_upload_id,
                    "linked_patient_encounter_id": row.linked_patient_encounter_id,
                    "linked_disease_name": row.linked_disease_name,
                    "lab_unit_name": row.lab_unit_name,
                    "lab_unit_id": row.lab_unit_id,
                }
            )

        return render_template(
            "admin/linked_task_inconsistencies.html",
            grouped=grouped,
            summary=summary,
            total=len(rows),
        )
