"""Utility functions for the results blueprint."""

from __future__ import annotations

import re

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session as SASession, joinedload, selectinload

from models import (
    
    Consensus,
    DiabeticRetinopathyReport,
    DirectImageUpload,
    EncounterFile,
    GlaucomaResultsCleaned,
    Grade,
    GradingTask,
    ImageGrading,
    LabUnit,
    PatientEncounters,
)


@dataclass(frozen=True)
class GradeSummary:
    """Render-friendly view of a single grade slot."""

    role: str
    impression: Optional[str]
    grader: Optional[str]
    comment: Optional[str]
    updated_at: Optional[str]


@dataclass(frozen=True)
class ConsensusSummary:
    """Compact representation of consensus metadata."""

    impression: Optional[str]
    method: Optional[str]
    decided_by: Optional[str]
    decided_at: Optional[str]


@dataclass(frozen=True)
class AIGradeSummary:
    """Summarize AI inference metadata for display."""

    model_name: str
    model_version: str
    impression: Optional[str]
    confidence: Optional[float]
    run_id: Optional[str]


def _summarize_grade(grade: Grade | None) -> Optional[GradeSummary]:
    if grade is None:
        return None
    impression = grade.label.impression if grade.label else None
    grader = grade.grader.username if grade.grader else None
    updated_at = grade.updated_at.isoformat() if grade.updated_at else None
    return GradeSummary(
        role=grade.role_slot,
        impression=impression,
        grader=grader,
        comment=grade.comment,
        updated_at=updated_at,
    )


def _summarize_consensus(consensus: Consensus | None) -> Optional[ConsensusSummary]:
    if consensus is None:
        return None
    impression = consensus.final_label.impression if consensus.final_label else consensus.final_grade_name
    decided_by = consensus.decided_by.username if consensus.decided_by else None
    decided_at = consensus.decided_at.isoformat() if consensus.decided_at else None
    return ConsensusSummary(
        impression=impression,
        method=consensus.method,
        decided_by=decided_by,
        decided_at=decided_at,
    )

'''
def _summarize_ai_grade(ai_grade: AIGrade) -> AIGradeSummary:
    impression = ai_grade.label.impression if ai_grade.label else None
    return AIGradeSummary(
        model_name=ai_grade.model_name,
        model_version=ai_grade.model_version,
        impression=impression,
        confidence=ai_grade.confidence,
        run_id=ai_grade.run_id,
    )
'''

def fetch_image_task_details(
    db: SASession,
    tasks: Sequence[GradingTask],
) -> List[Dict[str, Any]]:
    """Collect enriched details for the provided grading tasks.

    Args:
        db: Active SQLAlchemy session.
        tasks: Grading tasks that should be enriched with related data.

    Returns:
        A list of dictionaries, each containing presentation-ready data for one task.
    """

    if not tasks:
        return []

    task_ids = [task.id for task in tasks]

    encounter_ids = [task.encounter_file_id for task in tasks if task.encounter_file_id]
    direct_ids = [task.direct_image_upload_id for task in tasks if task.direct_image_upload_id]

    encounter_map: Dict[int, EncounterFile] = {}
    patient_encounter_ids: List[int] = []
    if encounter_ids:
        encounter_rows = (
            db.query(EncounterFile)
            .filter(EncounterFile.id.in_(encounter_ids))
            .options(
                joinedload(EncounterFile.patient_encounter)
                .joinedload(PatientEncounters.lab_unit)
                .joinedload(LabUnit.hospital),
            )
            .all()
        )
        for encounter in encounter_rows:
            encounter_map[encounter.id] = encounter
            if encounter.patient_encounter_id:
                patient_encounter_ids.append(encounter.patient_encounter_id)

    if patient_encounter_ids:
        patient_encounter_ids = list({pid for pid in patient_encounter_ids if pid is not None})

    direct_map: Dict[int, DirectImageUpload] = {}
    if direct_ids:
        direct_rows = (
            db.query(DirectImageUpload)
            .filter(DirectImageUpload.id.in_(direct_ids))
            .options(
                joinedload(DirectImageUpload.lab_unit).joinedload(LabUnit.hospital),
                selectinload(DirectImageUpload.camera),
                selectinload(DirectImageUpload.area),
            )
            .all()
        )
        for direct in direct_rows:
            direct_map[direct.id] = direct

    glaucoma_map: Dict[int, GlaucomaResultsCleaned] = {}
    if patient_encounter_ids:
        glaucoma_rows = (
            db.query(GlaucomaResultsCleaned)
            .filter(GlaucomaResultsCleaned.patient_encounter_id.in_(patient_encounter_ids))
            .all()
        )
        for row in glaucoma_rows:
            existing = glaucoma_map.get(row.patient_encounter_id)
            if existing is None or row.updated_at > existing.updated_at:
                glaucoma_map[row.patient_encounter_id] = row

    dr_map: Dict[int, DiabeticRetinopathyReport] = {}
    if patient_encounter_ids:
        dr_rows = (
            db.query(DiabeticRetinopathyReport)
            .filter(DiabeticRetinopathyReport.patient_encounter_id.in_(patient_encounter_ids))
            .all()
        )
        for row in dr_rows:
            existing = dr_map.get(row.patient_encounter_id)
            if existing is None or row.id > existing.id:
                dr_map[row.patient_encounter_id] = row

    grades_by_task: Dict[int, Dict[str, Grade]] = {task_id: {} for task_id in task_ids}
    grade_rows = (
        db.query(Grade)
        .filter(Grade.task_id.in_(task_ids))
        .options(selectinload(Grade.label), selectinload(Grade.grader))
        .all()
    )
    for grade in grade_rows:
        grades_by_task.setdefault(grade.task_id, {})[grade.role_slot] = grade

    # Fetch AI grades that are stored as Grade objects with role_slot = 'ai'
    # These are linked to the image via the GradingTask
    ai_grades_by_task: Dict[int, List[Grade]] = {}
    ai_grade_rows = (
        db.query(Grade)
        .filter(Grade.task_id.in_(task_ids), Grade.role_slot == 'ai')
        .options(selectinload(Grade.label), selectinload(Grade.grader), selectinload(Grade.ai_model))
        .all()
    )
    for ai_grade in ai_grade_rows:
        ai_grades_by_task.setdefault(ai_grade.task_id, []).append(ai_grade)

    consensus_map: Dict[int, Consensus] = {}
    consensus_rows = (
        db.query(Consensus)
        .filter(Consensus.task_id.in_(task_ids))
        .options(selectinload(Consensus.final_label), selectinload(Consensus.decided_by))
        .all()
    )
    for consensus in consensus_rows:
        consensus_map[consensus.task_id] = consensus



    details: List[Dict[str, Any]] = []
    for task in tasks:
        encounter = encounter_map.get(task.encounter_file_id) if task.encounter_file_id else None
        direct_image = direct_map.get(task.direct_image_upload_id) if task.direct_image_upload_id else None

        patient_encounter = encounter.patient_encounter if encounter else None
        patient_encounter_id = patient_encounter.id if patient_encounter else None

        glaucoma_cleaned = glaucoma_map.get(patient_encounter_id) if patient_encounter_id else None
        dr_report = dr_map.get(patient_encounter_id) if patient_encounter_id else None

        hospital_name = None
        lab_unit_name = None
        if task.lab_unit:
            lab_unit_name = task.lab_unit.name
            if task.lab_unit.hospital:
                hospital_name = task.lab_unit.hospital.name

        image_uuid = None
        image_type = None
        eye_side = None
        upload_type = "unknown"
        is_zip_image = False

        if encounter:
            image_uuid = encounter.uuid
            image_type = encounter.file_type
            eye_side = encounter.eye_side
            upload_type = "zip"
            if patient_encounter and patient_encounter.zip_file_id:
                is_zip_image = True
        elif direct_image:
            image_uuid = direct_image.uuid
            image_type = direct_image.area.name if direct_image.area else None
            upload_type = "direct"
            hospital_name = hospital_name or (direct_image.lab_unit.hospital.name if direct_image.lab_unit and direct_image.lab_unit.hospital else None)
            lab_unit_name = lab_unit_name or (direct_image.lab_unit.name if direct_image.lab_unit else None)

        grade_map = grades_by_task.get(task.id, {})
        resident_grade = _summarize_grade(grade_map.get("resident"))
        faculty_grade = _summarize_grade(grade_map.get("faculty"))
        arbitrator_grade = _summarize_grade(grade_map.get("arbitrator"))

        consensus_summary = _summarize_consensus(consensus_map.get(task.id))

        ai_key = (task.encounter_file_id, task.direct_image_upload_id)
        # Get AIGrade objects for this image and disease

        # Get Grade objects with role_slot='ai' for this task
        ai_grade_from_grade_table = ai_grades_by_task.get(task.id, [])
        # Combine both types of AI grades
        all_ai_grades =  ai_grade_from_grade_table
        # Summarize them for the template
        ai_grades = []
        for obj in all_ai_grades:
            # It's a Grade object with role_slot='ai'
                # Use the AI model details from the Grade object itself
            ai_grades.append(AIGradeSummary(
                model_name=obj.ai_model_name or (obj.ai_model.name if obj.ai_model else 'Unknown Model'),
                model_version=obj.ai_model_version or (obj.ai_model.version if obj.ai_model else 'N/A'),
                impression=obj.label.impression if obj.label else obj.grade_name,
                # Extract probability from comment if it's in the format "AI probability: X.XX; ..." or similar
                confidence=float(re.search(r'AI probability:\s*([0-9.]+)', obj.comment or "").group(1)) if re.search(r'AI probability:\s*([0-9.]+)', obj.comment or "") else None,
                run_id=None # Grade model doesn't have run_id
            ))

        details.append(
            {
                "task_id": task.id,
                "encounter_file_id": task.encounter_file_id,
                "direct_image_upload_id": task.direct_image_upload_id,
                "image_uuid": image_uuid,
                "disease_name": task.disease.name if task.disease else None,
                "upload_type": upload_type,
                "is_zip_image": is_zip_image,
                "image_type": image_type,
                "eye_side": eye_side,
                "hospital_name": hospital_name,
                "lab_unit_name": lab_unit_name,
                "resident_grade": resident_grade,
                "faculty_grade": faculty_grade,
                "arbitrator_grade": arbitrator_grade,
                "consensus": consensus_summary,
                "ai_grades": ai_grades,
                "glaucoma_result": glaucoma_cleaned.result if glaucoma_cleaned else None,
                "glaucoma_vcdr_right": glaucoma_cleaned.vcdr_right_num if glaucoma_cleaned else None,
                "glaucoma_vcdr_left": glaucoma_cleaned.vcdr_left_num if glaucoma_cleaned else None,
                "dr_result": dr_report.result if dr_report else None,
                "dr_qualitative_result": dr_report.qualitative_result if dr_report else None,
                "graded_state": task.state,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
            }
        )

    return details


def _latest_glaucoma_cleaned(glaucoma_rows: Sequence[GlaucomaResultsCleaned]) -> Optional[Dict[str, Any]]:
    if not glaucoma_rows:
        return None
    latest = max(glaucoma_rows, key=lambda row: row.updated_at or row.created_at)
    return {
        "result": latest.result,
        "qualitative_result": latest.qualitative_result,
        "vcdr_right": latest.vcdr_right_num,
        "vcdr_left": latest.vcdr_left_num,
        "report_uuid": latest.report_uuid,
        "report_file_name": latest.report_file_name,
        "updated_at": latest.updated_at,
    }


def _latest_dr_report(dr_rows: Sequence[DiabeticRetinopathyReport]) -> Optional[Dict[str, Any]]:
    if not dr_rows:
        return None
    latest = max(dr_rows, key=lambda row: row.id)
    return {
        "result": latest.result,
        "qualitative_result": latest.qualitative_result,
        "report_file_name": latest.report_file_name,
    }


def group_task_details_by_image(task_details: Sequence[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    mapping: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for detail in task_details:
        image_id = detail.get("encounter_file_id")
        if image_id is not None:
            mapping[int(image_id)].append(detail)
    for details in mapping.values():
        details.sort(key=lambda item: (item.get("disease_name") or "", item.get("task_id") or 0))
    return mapping


def build_encounter_result_payload(
    encounters: Sequence[PatientEncounters],
    task_details: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    tasks_by_image = group_task_details_by_image(task_details)
    payload: List[Dict[str, Any]] = []

    for encounter in encounters:
        glaucoma_info = _latest_glaucoma_cleaned(encounter.glaucoma_results_cleaned)
        dr_info = _latest_dr_report(encounter.dr_reports)

        images: List[Dict[str, Any]] = []
        for image in sorted(encounter.encounter_files, key=lambda ef: ((ef.eye_side or ""), ef.id)):
            legacy_gradings: List[Dict[str, Any]] = []
            for grading in sorted(image.gradings, key=lambda g: g.updated_at or g.created_at):
                legacy_gradings.append(
                    {
                        "graded_for": grading.graded_for,
                        "impression": grading.impression,
                        "grader": grading.grader_username or (grading.grader.username if grading.grader else None),
                        "updated_at": grading.updated_at,
                    }
                )

            images.append(
                {
                    "id": image.id,
                    "uuid": image.uuid,
                    "eye_side": image.eye_side,
                    "file_type": image.file_type,
                    "tasks": tasks_by_image.get(image.id, []),
                    "legacy_gradings": legacy_gradings,
                }
            )

        payload.append(
            {
                "encounter": encounter,
                "glaucoma": glaucoma_info,
                "dr": dr_info,
                "images": images,
            }
        )

    return payload
