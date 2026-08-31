"""Authorization lineage for persisted uploads.

Camera, disease, area, mydriatic state, file content, and profile option
validation deliberately remain in the upload services.
"""

from __future__ import annotations

from sqlalchemy import select

from authz import AuthorizationDenied, RecordColumns, RecordScope


def upload_record_scope(upload) -> RecordScope:
    """Return complete immutable scope facts for one upload, or deny."""
    lab_unit_id = getattr(upload, "lab_unit_id", None)
    hospital_id = getattr(upload, "hospital_id", None)
    project_id = getattr(upload, "project_id", None)
    if lab_unit_id is None or hospital_id is None:
        raise AuthorizationDenied("upload_lineage_missing")
    if project_id is None:
        return RecordScope.classical(
            lab_unit_id=lab_unit_id,
            hospital_id=hospital_id,
        )
    return RecordScope.project(
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        hospital_id=hospital_id,
    )


def encounter_record_scope(context, encounter) -> RecordScope:
    """Resolve an encounter's project/Lab Unit/hospital lineage or deny."""
    lab_unit_id = getattr(encounter, "lab_unit_id", None)
    if lab_unit_id is None:
        raise AuthorizationDenied("encounter_lab_unit_missing")
    hospital_id = getattr(getattr(encounter, "lab_unit", None), "hospital_id", None)
    if hospital_id is None:
        from models import LabUnit

        hospital_id = context.db.execute(
            select(LabUnit.hospital_id).where(LabUnit.id == int(lab_unit_id))
        ).scalar_one_or_none()
    if hospital_id is None:
        raise AuthorizationDenied("encounter_hospital_lineage_missing")
    project_id = getattr(encounter, "project_id", None)
    if project_id is None:
        return RecordScope.classical(
            lab_unit_id=int(lab_unit_id), hospital_id=int(hospital_id)
        )
    return RecordScope.project(
        project_id=int(project_id),
        lab_unit_id=int(lab_unit_id),
        hospital_id=int(hospital_id),
    )


def upload_columns(model) -> RecordColumns:
    """Columns for SQL scoping of an upload model with canonical lineage."""
    required = ("project_id", "hospital_id", "lab_unit_id", "uploader_id")
    if any(not hasattr(model, name) for name in required):
        return RecordColumns()
    return RecordColumns(
        project_id=model.project_id,
        hospital_id=model.hospital_id,
        lab_unit_id=model.lab_unit_id,
        user_id=model.uploader_id,
    )


def encounter_columns(model) -> RecordColumns:
    """Columns for an encounter whose hospital is derived from its Lab Unit."""
    if not all(hasattr(model, name) for name in ("project_id", "lab_unit_id")):
        return RecordColumns()
    return RecordColumns(project_id=model.project_id, lab_unit_id=model.lab_unit_id)


def encounter_file_columns(model) -> RecordColumns:
    """Columns for an encounter file with persisted authorization lineage."""
    if not all(
        hasattr(model, name) for name in ("project_id", "hospital_id", "lab_unit_id")
    ):
        return RecordColumns()
    return RecordColumns(
        project_id=model.project_id,
        hospital_id=model.hospital_id,
        lab_unit_id=model.lab_unit_id,
    )
