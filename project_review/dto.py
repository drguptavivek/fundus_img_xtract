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
    help_text: str | None = None


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
class ProjectSourceDTO:
    id: str
    kind: str
    name: str
    summary: str
    badges: tuple[str, ...]
    details: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProjectAnalysisDTO:
    id: int
    mode: str
    model: str
    provider: str
    disease: str
    upload_kind: str
    trigger: str
    eligibility: str
    image_selection: str


@dataclass(frozen=True)
class GradeChoiceDTO:
    impression: str
    guidelines: str
    features: tuple[str, ...]


@dataclass(frozen=True)
class DiseaseDefinitionDTO:
    disease: str
    target_level: str
    relationship: str
    grades: tuple[GradeChoiceDTO, ...]


@dataclass(frozen=True)
class GradingTargetDTO:
    id: str
    target_type: str
    disease: str
    profile: str
    encounter_set_type: str
    package: str
    grading_mode: str
    task_creation: str
    package_applicability: str
    image_rules: tuple[str, ...]
    definitions: tuple[DiseaseDefinitionDTO, ...]


@dataclass(frozen=True)
class AnnotationConfigurationDTO:
    revision: int
    default_localization: str
    preferred_tool: str
    tools: tuple[str, ...]
    classes: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class MetadataFieldDTO:
    key: str
    label: str
    scope: str
    field_type: str
    requirement: str
    verifier_editable: bool
    is_pii: bool
    choices: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ConfiguredUserDTO:
    id: int
    name: str
    scopes: tuple[str, ...]
    roles: tuple[str, ...]
    upload_assignments: tuple[str, ...]
    grading_allocations: tuple[str, ...]


@dataclass(frozen=True)
class ReferralDiseaseDTO:
    disease: str
    source: str


@dataclass(frozen=True)
class ProjectSummaryDTO:
    project: ProjectChoiceDTO
    scope: ProjectScopeDTO
    metrics: tuple[ProjectMetricDTO, ...]
    profiles: tuple[ProjectProfileDTO, ...]
    sources: tuple[ProjectSourceDTO, ...]
    automated_analyses: tuple[ProjectAnalysisDTO, ...]
    grading_targets: tuple[GradingTargetDTO, ...]
    annotation: AnnotationConfigurationDTO | None
    metadata_fields: tuple[MetadataFieldDTO, ...]
    configured_users: tuple[ConfiguredUserDTO, ...]
    referral_diseases: tuple[ReferralDiseaseDTO, ...]
    grading_rows: tuple[ProjectGradingDTO, ...]
    grading_stage_metrics: tuple[ProjectMetricDTO, ...]
    grading_completion_percent: int


@dataclass(frozen=True)
class ProjectUploadDTO:
    entity_type: str
    uuid: str
    source: str
    hospital_name: str
    lab_unit_name: str
    lab_unit_id: int
    status: str
    image_count: int
    uploaded_at: date | datetime | None
    upload_id: int | None = None
    filename: str | None = None
    uploader_name: str | None = None
    disease_name: str | None = None
    upload_remarks: str | None = None
    can_verify: bool = False


@dataclass(frozen=True)
class ProjectLabUnitChoiceDTO:
    id: int
    name: str
    hospital_name: str


@dataclass(frozen=True)
class ProjectUploadPageDTO:
    project: ProjectChoiceDTO
    scope: ProjectScopeDTO
    rows: tuple[ProjectUploadDTO, ...]
    lab_units: tuple[ProjectLabUnitChoiceDTO, ...]
    totals: tuple[ProjectMetricDTO, ...]
    page: int
    per_page: int
    total_rows: int


@dataclass(frozen=True)
class DirectImageVerificationDTO:
    project_id: int
    upload_id: int
    uuid: str
    filename: str
    image_url_uuid: str
    uploaded_at: datetime
    disease_name: str
    hospital_name: str
    lab_unit_name: str
    camera_name: str
    area_name: str
    uploader_name: str
    verification_status: str
    remarks: str
    upload_remarks: str | None
    pii_status: str | None
    pii_source: str | None
    pii_checked_at: datetime | None
    can_edit: bool


@dataclass(frozen=True)
class ProjectGradingDTO:
    target_group: str
    target_type: str
    grading_mode: str
    scope_role: str | None
    scope_name: str | None
    parent_scope_name: str | None
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
