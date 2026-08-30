"""Strict classical lineage predicates for legacy maintenance backfills."""

from sqlalchemy import and_, exists, select

from models import DirectImageUpload, EncounterFile, LabUnit, PatientEncounters


def strict_encounter_scope(query, allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return query.filter(False)
    return query.join(LabUnit, LabUnit.id == EncounterFile.lab_unit_id).filter(
        and_(
            EncounterFile.project_id.is_(None),
            PatientEncounters.project_id.is_(None),
            EncounterFile.lab_unit_id.is_not(None),
            PatientEncounters.lab_unit_id == EncounterFile.lab_unit_id,
            EncounterFile.hospital_id.is_not(None),
            EncounterFile.hospital_id == LabUnit.hospital_id,
            EncounterFile.lab_unit_id.in_(allowed_lab_unit_ids),
        )
    )


def strict_direct_scope(query, allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return query.filter(False)
    return query.join(LabUnit, LabUnit.id == DirectImageUpload.lab_unit_id).filter(
        and_(
            DirectImageUpload.project_id.is_(None),
            DirectImageUpload.hospital_id == LabUnit.hospital_id,
            DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids),
        )
    )


def strict_direct_condition(allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return False
    valid_lab = exists(
        select(LabUnit.id).where(
            LabUnit.id == DirectImageUpload.lab_unit_id,
            LabUnit.hospital_id == DirectImageUpload.hospital_id,
        )
    )
    return and_(
        DirectImageUpload.project_id.is_(None),
        DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids),
        valid_lab,
    )
