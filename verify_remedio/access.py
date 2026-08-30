"""Authorization helpers shared by the legacy Remedio verification views.

These blueprints are the pre-project verification workflow.  They therefore
authorize only classical encounters: an assigned uploader/optometrist lab or
the hospital-wide manager roles may see the row, and a project encounter is
never admitted merely because it reuses one of those lab units.

The predicate is applied to the query that loads the encounter (or a report
joined to its encounter), before ``first()``/``all()`` and before mutations.
Workflow and field validation remain in the route/service layer.
"""

from __future__ import annotations

from authz.context import access_context
from sqlalchemy import exists, select
from sqlalchemy.orm.attributes import set_committed_value

from authz.rows import RecordColumns, role_scoped_rows
from models import EncounterFile, LabUnit, PatientEncounters


def classical_verification_rows(db, query, user):
    """Restrict a verification query to authorized classical encounters."""

    scoped = role_scoped_rows(
        query,
        access_context(db, user),
        RecordColumns(
            project_id=PatientEncounters.project_id,
            lab_unit_id=PatientEncounters.lab_unit_id,
        ),
        lab_roles={"fileuploader", "optometrist"},
        hospital_roles={"local_admin", "data_manager"},
        allow_admin=True,
    )
    # Admin bypasses role membership, not data lineage.  Legacy verification
    # can only operate on classical encounters with a valid Lab Unit whose
    # hospital relationship is present.
    return scoped.filter(
        PatientEncounters.project_id.is_(None),
        PatientEncounters.lab_unit_id.is_not(None),
        exists(
            select(LabUnit.id).where(
                LabUnit.id == PatientEncounters.lab_unit_id,
                LabUnit.hospital_id.is_not(None),
            )
        ),
    )


def classical_verification_files(db, query, user):
    """Scope child images to an authorized classical encounter and lineage."""

    scoped = classical_verification_rows(
        db,
        query.join(
            PatientEncounters,
            EncounterFile.patient_encounter_id == PatientEncounters.id,
        ),
        user,
    )
    return scoped.filter(
        EncounterFile.project_id.is_(None),
        EncounterFile.lab_unit_id.is_not(None),
        EncounterFile.hospital_id.is_not(None),
        EncounterFile.lab_unit_id == PatientEncounters.lab_unit_id,
        exists(
            select(LabUnit.id).where(
                LabUnit.id == EncounterFile.lab_unit_id,
                LabUnit.hospital_id == EncounterFile.hospital_id,
                LabUnit.hospital_id.is_not(None),
            )
        ),
    )


def consistent_verification_files(encounter):
    """Return only complete child lineage for an already scoped encounter."""

    lab_unit = getattr(encounter, "lab_unit", None)
    parent_lab_id = getattr(encounter, "lab_unit_id", None)
    parent_hospital_id = getattr(lab_unit, "hospital_id", None)
    if not parent_lab_id or not parent_hospital_id:
        return []
    files = [
        file
        for file in (getattr(encounter, "encounter_files", None) or [])
        if file.project_id is None
        and file.lab_unit_id == parent_lab_id
        and file.hospital_id == parent_hospital_id
    ]
    # Keep templates on the same vetted collection without marking malformed
    # rows as deleted by SQLAlchemy's delete-orphan relationship machinery.
    set_committed_value(encounter, "encounter_files", files)
    return files


__all__ = [
    "classical_verification_files",
    "classical_verification_rows",
    "consistent_verification_files",
]
