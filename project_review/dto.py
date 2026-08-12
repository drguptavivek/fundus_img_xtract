"""Typed contracts for the project review workspace."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ProjectChoiceDTO:
    id: int
    title: str
    code: str
    active: bool


@dataclass(frozen=True)
class ProjectScopeDTO:
    project_wide: bool
    hospital_ids: tuple[int, ...]
    lab_unit_ids: tuple[int, ...]
    label: str


@dataclass(frozen=True)
class ProjectMetricDTO:
    key: str
    label: str
    value: int


@dataclass(frozen=True)
class ProjectProfileDTO:
    name: str
    active: bool
    upload_kinds: tuple[str, ...]
    diseases: tuple[str, ...]
    encounter_set_types: tuple[str, ...]
    grading_packages: tuple[str, ...]
    remidio_api_enabled: bool
    iitk_enabled: bool


@dataclass(frozen=True)
class ProjectSummaryDTO:
    project: ProjectChoiceDTO
    scope: ProjectScopeDTO
    metrics: tuple[ProjectMetricDTO, ...]
    profiles: tuple[ProjectProfileDTO, ...]


@dataclass(frozen=True)
class ProjectUploadDTO:
    entity_type: str
    uuid: str
    source: str
    hospital_name: str
    lab_unit_name: str
    status: str
    image_count: int
    uploaded_at: date | datetime | None


@dataclass(frozen=True)
class ProjectUploadPageDTO:
    project: ProjectChoiceDTO
    scope: ProjectScopeDTO
    rows: tuple[ProjectUploadDTO, ...]
    totals: tuple[ProjectMetricDTO, ...]
    page: int
    per_page: int
    total_rows: int


@dataclass(frozen=True)
class ProjectGradingDTO:
    target_type: str
    grading_mode: str
    disease_name: str
    state: str
    state_label: str
    task_count: int
    image_count: int


@dataclass(frozen=True)
class ProjectGradingsDTO:
    project: ProjectChoiceDTO
    scope: ProjectScopeDTO
    rows: tuple[ProjectGradingDTO, ...]
    totals: tuple[ProjectMetricDTO, ...]
