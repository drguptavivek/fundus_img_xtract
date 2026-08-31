"""Structural integrity predicates for grading-task source relationships."""

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from models import (
    DirectImageUpload,
    EncounterFile,
    EncounterSetImage,
    GradingTask,
    LabUnit,
    PatientEncounters,
)


def valid_task_lineage(task=GradingTask):
    """Require exactly one complete source whose scope agrees with the task."""
    task_lab = aliased(LabUnit)
    task_hospital_id = (
        select(task_lab.hospital_id)
        .where(task_lab.id == task.lab_unit_id)
        .correlate(task)
        .scalar_subquery()
    )
    valid_lab = aliased(LabUnit)
    valid_task_lab = exists(
        select(1).select_from(valid_lab).correlate(task).where(
            valid_lab.id == task.lab_unit_id,
            valid_lab.hospital_id.is_not(None),
        )
    )
    source_shape = or_(
        and_(task.encounter_file_id.is_not(None), task.direct_image_upload_id.is_(None), task.patient_encounter_id.is_(None), task.encounter_set_image_id.is_(None)),
        and_(task.encounter_file_id.is_(None), task.direct_image_upload_id.is_not(None), task.patient_encounter_id.is_(None), task.encounter_set_image_id.is_(None)),
        and_(task.encounter_file_id.is_(None), task.direct_image_upload_id.is_(None), task.patient_encounter_id.is_not(None), task.encounter_set_image_id.is_(None)),
        and_(task.encounter_file_id.is_(None), task.direct_image_upload_id.is_(None), task.patient_encounter_id.is_(None), task.encounter_set_image_id.is_not(None)),
    )
    encounter_file = exists(
        select(1).select_from(EncounterFile).join(
            PatientEncounters, PatientEncounters.id == EncounterFile.patient_encounter_id
        ).correlate(task).where(
            EncounterFile.id == task.encounter_file_id,
            PatientEncounters.lab_unit_id == task.lab_unit_id,
            or_(EncounterFile.lab_unit_id.is_(None), EncounterFile.lab_unit_id == task.lab_unit_id),
            or_(EncounterFile.hospital_id.is_(None), EncounterFile.hospital_id == task_hospital_id),
            or_(EncounterFile.project_id.is_(None), EncounterFile.project_id == PatientEncounters.project_id),
            PatientEncounters.project_id.is_not_distinct_from(task.project_id),
        )
    )
    direct = exists(select(1).select_from(DirectImageUpload).correlate(task).where(
        DirectImageUpload.id == task.direct_image_upload_id,
        DirectImageUpload.lab_unit_id == task.lab_unit_id,
        DirectImageUpload.hospital_id == task_hospital_id,
        DirectImageUpload.project_id.is_not_distinct_from(task.project_id),
    ))
    encounter = exists(select(1).select_from(PatientEncounters).correlate(task).where(
        PatientEncounters.id == task.patient_encounter_id,
        PatientEncounters.lab_unit_id == task.lab_unit_id,
        PatientEncounters.project_id.is_not_distinct_from(task.project_id),
    ))
    set_image = exists(
        select(1).select_from(EncounterSetImage).join(
            PatientEncounters, PatientEncounters.id == EncounterSetImage.patient_encounter_id
        ).correlate(task).where(
            EncounterSetImage.id == task.encounter_set_image_id,
            or_(EncounterSetImage.hospital_id.is_(None), EncounterSetImage.hospital_id == task_hospital_id),
            PatientEncounters.lab_unit_id == task.lab_unit_id,
            or_(EncounterSetImage.project_id.is_(None), EncounterSetImage.project_id == PatientEncounters.project_id),
            PatientEncounters.project_id.is_not_distinct_from(task.project_id),
        )
    )
    return and_(
        task.lab_unit_id.is_not(None),
        valid_task_lab,
        source_shape,
        or_(
            and_(task.encounter_file_id.is_not(None), encounter_file),
            and_(task.direct_image_upload_id.is_not(None), direct),
            and_(task.patient_encounter_id.is_not(None), encounter),
            and_(task.encounter_set_image_id.is_not(None), set_image),
        ),
    )
