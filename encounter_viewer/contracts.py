"""Detached DTO contracts for the encounter evidence viewer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VIEWER_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class ViewerGradeDTO:
    role_slot: str
    label: str
    model: str | None = None
    review_status: str | None = None


@dataclass(frozen=True)
class ViewerAnnotationDTO:
    label: str
    geometry_type: str
    geometry: dict[str, Any] | None = None


@dataclass(frozen=True)
class ViewerTargetDTO:
    task_uuid: str
    disease: str
    target_level: str
    state: str
    final_label: str | None
    final_method: str | None
    grades: tuple[ViewerGradeDTO, ...] = ()
    annotations: tuple[ViewerAnnotationDTO, ...] = ()


@dataclass(frozen=True)
class ViewerImageDTO:
    source_type: str
    source_id: int
    uuid: str
    position: int
    laterality: str
    focus: str | None
    camera: str | None
    media_url: str
    thumbnail_url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    targets: tuple[ViewerTargetDTO, ...] = ()


@dataclass(frozen=True)
class ViewerInferenceDTO:
    provider: str
    disease: str
    result: str | None
    status: str | None = None
    model: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    count: int = 1


@dataclass(frozen=True)
class ViewerActionDTO:
    kind: str
    label: str
    url: str


@dataclass(frozen=True)
class EncounterViewerDTO:
    resource_kind: str
    resource_id: str
    source_kind: str
    capture_date: str | None
    project_code: str | None
    hospital: str | None
    lab_unit: str | None
    verified_status: str | None
    can_view_clinical_results: bool
    images: tuple[ViewerImageDTO, ...]
    encounter_targets: tuple[ViewerTargetDTO, ...] = ()
    inferences: tuple[ViewerInferenceDTO, ...] = ()
    actions: tuple[ViewerActionDTO, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = VIEWER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
