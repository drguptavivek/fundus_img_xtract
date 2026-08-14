"""Task-backed filter options for discrepancy review."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from encounter_sets.permissions import (
    CAPABILITY_DATA_EXPORT,
    CAPABILITY_DISCREPANCY_REVIEW,
    capability_lab_unit_ids,
    project_task_capability_clause,
)
from models import (
    Disease,
    DirectImageUpload,
    EncounterFile,
    EncounterSetImage,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
    Project,
    User,
)


class DiscrepancyScopeError(ValueError):
    """Raised when a requested project is outside the caller's task scope."""


def discrepancy_lab_unit_ids(db: Session, *, user: User) -> set[int]:
    """Return the union of discrepancy-review and export lab scope."""
    return capability_lab_unit_ids(
        db,
        user=user,
        capability=CAPABILITY_DISCREPANCY_REVIEW,
    ) | capability_lab_unit_ids(
        db,
        user=user,
        capability=CAPABILITY_DATA_EXPORT,
    )


@dataclass(frozen=True)
class ProjectFilterOption:
    id: int
    title: str
    active: bool

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "title": self.title, "active": self.active}


@dataclass(frozen=True)
class DiseaseFilterOption:
    id: int
    name: str

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name}


@dataclass(frozen=True)
class LabUnitFilterOption:
    id: int
    name: str
    hospital_id: int
    hospital_name: str

    @property
    def label(self) -> str:
        return f"{self.hospital_name} - {self.name}"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "hospital_id": self.hospital_id,
            "hospital_name": self.hospital_name,
            "label": self.label,
        }


@dataclass(frozen=True)
class DiscrepancyFilterOptions:
    projects: tuple[ProjectFilterOption, ...]
    diseases: tuple[DiseaseFilterOption, ...]
    lab_units: tuple[LabUnitFilterOption, ...]
    project_id: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "projects": [option.to_dict() for option in self.projects],
            "diseases": [option.to_dict() for option in self.diseases],
            "lab_units": [option.to_dict() for option in self.lab_units],
        }


def _task_scope_query(
    db: Session,
    *,
    user: User,
    allowed_lab_unit_ids: set[int],
):
    task_encounter = aliased(PatientEncounters)
    set_image = aliased(EncounterSetImage)
    set_encounter = aliased(PatientEncounters)
    encounter_file = aliased(EncounterFile)
    file_encounter = aliased(PatientEncounters)
    direct_image = aliased(DirectImageUpload)
    project_id = func.coalesce(
        task_encounter.project_id,
        set_image.project_id,
        set_encounter.project_id,
        encounter_file.project_id,
        file_encounter.project_id,
        direct_image.project_id,
    )
    query = (
        db.query(GradingTask)
        .outerjoin(task_encounter, task_encounter.id == GradingTask.patient_encounter_id)
        .outerjoin(set_image, set_image.id == GradingTask.encounter_set_image_id)
        .outerjoin(set_encounter, set_encounter.id == set_image.patient_encounter_id)
        .outerjoin(encounter_file, encounter_file.id == GradingTask.encounter_file_id)
        .outerjoin(file_encounter, file_encounter.id == encounter_file.patient_encounter_id)
        .outerjoin(direct_image, direct_image.id == GradingTask.direct_image_upload_id)
        .filter(GradingTask.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(
            or_(
                project_task_capability_clause(
                    GradingTask.id, user, CAPABILITY_DISCREPANCY_REVIEW
                ),
                project_task_capability_clause(
                    GradingTask.id, user, CAPABILITY_DATA_EXPORT
                ),
            )
        )
    )
    return query, project_id


def list_discrepancy_filter_options(
    db: Session,
    *,
    user: User,
    allowed_lab_unit_ids: set[int],
    project_id: int | None = None,
) -> DiscrepancyFilterOptions:
    """Return projects and task-backed disease/lab options in caller scope."""
    if not allowed_lab_unit_ids:
        return DiscrepancyFilterOptions((), (), (), project_id)

    base_query, source_project_id = _task_scope_query(
        db,
        user=user,
        allowed_lab_unit_ids=allowed_lab_unit_ids,
    )
    project_rows = (
        base_query.with_entities(Project.id, Project.title, Project.active)
        .join(Project, Project.id == source_project_id)
        .distinct()
        .order_by(Project.title, Project.id)
        .all()
    )
    projects = tuple(
        ProjectFilterOption(row.id, row.title, row.active) for row in project_rows
    )
    if project_id is not None and project_id not in {option.id for option in projects}:
        raise DiscrepancyScopeError("Project is unavailable for discrepancy review.")

    option_query = base_query
    if project_id is not None:
        option_query = option_query.filter(source_project_id == project_id)

    disease_rows = (
        option_query.with_entities(Disease.id, Disease.name)
        .join(Disease, Disease.id == GradingTask.disease_id)
        .distinct()
        .order_by(Disease.name, Disease.id)
        .all()
    )
    lab_rows = (
        option_query.with_entities(
            LabUnit.id,
            LabUnit.name,
            LabUnit.hospital_id,
            Hospital.name.label("hospital_name"),
        )
        .join(LabUnit, LabUnit.id == GradingTask.lab_unit_id)
        .join(Hospital, Hospital.id == LabUnit.hospital_id)
        .distinct()
        .order_by(LabUnit.hospital_id, LabUnit.name, LabUnit.id)
        .all()
    )
    return DiscrepancyFilterOptions(
        projects=projects,
        diseases=tuple(DiseaseFilterOption(row.id, row.name) for row in disease_rows),
        lab_units=tuple(
            LabUnitFilterOption(
                row.id,
                row.name,
                row.hospital_id,
                row.hospital_name,
            )
            for row in lab_rows
        ),
        project_id=project_id,
    )
