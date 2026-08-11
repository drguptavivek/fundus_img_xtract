from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass(frozen=True)
class ProjectDTO:
    id: int
    title: str
    code: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CaptureDateDTO:
    date: date
    encounter_count: int

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "encounter_count": self.encounter_count}


@dataclass(frozen=True)
class EncounterDTO:
    id: int
    uuid: str
    remidio_exam_id: str
    capture_date: date
    verification_status: str
    image_count: int
    attachment_count: int
    task_count: int
    grade_count: int
    package_count: int
    movable: bool
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["capture_date"] = self.capture_date.isoformat()
        data["blockers"] = list(self.blockers)
        return data


@dataclass(frozen=True)
class MigrationPreviewDTO:
    source_project: ProjectDTO
    target_project: ProjectDTO
    capture_date: date
    encounters: tuple[EncounterDTO, ...]
    target_project_upload_profile_id: int
    target_upload_profile_id: int
    target_upload_profile_name: str
    target_binding_ids: tuple[int, ...]
    warnings: tuple[str, ...]
    confirmation_token: str
    task_count: int
    grade_count: int
    package_count: int

    def to_dict(self) -> dict:
        return {
            "source_project": self.source_project.to_dict(),
            "target_project": self.target_project.to_dict(),
            "capture_date": self.capture_date.isoformat(),
            "encounters": [row.to_dict() for row in self.encounters],
            "target_project_upload_profile_id": self.target_project_upload_profile_id,
            "target_upload_profile_id": self.target_upload_profile_id,
            "target_upload_profile_name": self.target_upload_profile_name,
            "target_binding_ids": list(self.target_binding_ids),
            "warnings": list(self.warnings),
            "confirmation_token": self.confirmation_token,
            "task_count": self.task_count,
            "grade_count": self.grade_count,
            "package_count": self.package_count,
        }


@dataclass(frozen=True)
class MigrationResultDTO:
    moved_encounter_ids: tuple[int, ...]
    source_project_id: int
    target_project_id: int
    tasks_reset: int
    grades_reset: int
    packages_reset: int
    sessions_invalidated: int
    audit_id: int

    def to_dict(self) -> dict:
        data = asdict(self)
        data["moved_encounter_ids"] = list(self.moved_encounter_ids)
        return data
