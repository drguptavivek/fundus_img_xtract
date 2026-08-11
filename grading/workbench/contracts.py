"""Detached DTO contracts shared by workbench APIs and HTML views."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


WORKBENCH_SCHEMA_VERSION = 1
ANNOTATION_SCHEMA_VERSION = 1


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(frozen=True)
class WorkbenchLeaseDTO:
    session_uuid: str
    role_slot: str
    workflow: str
    token_generation: int
    acquired_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    heartbeat_interval_seconds: int = 60
    expiry_warning_seconds: int = 300

    def to_dict(self) -> dict[str, object]:
        return {
            "session_uuid": self.session_uuid,
            "role_slot": self.role_slot,
            "workflow": self.workflow,
            "token_generation": self.token_generation,
            "acquired_at": _iso(self.acquired_at),
            "idle_expires_at": _iso(self.idle_expires_at),
            "absolute_expires_at": _iso(self.absolute_expires_at),
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "expiry_warning_seconds": self.expiry_warning_seconds,
        }


@dataclass(frozen=True)
class WorkbenchMediaDTO:
    source_type: str
    image_uuid: str
    media_url: str
    thumbnail_url: str | None = None
    laterality: str | None = None
    width: int | None = None
    height: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkbenchFeatureDTO:
    id: int
    label: str
    sr_no: int | None


@dataclass(frozen=True)
class WorkbenchGradeOptionDTO:
    id: int
    impression: str
    guidelines: str | None
    features: tuple[WorkbenchFeatureDTO, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "impression": self.impression,
            "guidelines": self.guidelines,
            "features": [asdict(item) for item in self.features],
        }


@dataclass(frozen=True)
class WorkbenchAnnotationDTO:
    enabled: bool
    policy_source: str
    project_id: int | None
    policy_revision: int
    enabled_tools: tuple[str, ...]
    default_feature_policy: dict[str, Any]
    project_classes: tuple[dict[str, Any], ...]
    annotation_set_uuid: str | None = None
    instances: tuple[dict[str, Any], ...] = ()
    legacy_geometry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "policy_source": self.policy_source,
            "project_id": self.project_id,
            "policy_revision": self.policy_revision,
            "revision": self.policy_revision,
            "enabled_tools": list(self.enabled_tools),
            "default_feature_policy": self.default_feature_policy,
            "project_classes": list(self.project_classes),
            "annotation_set_uuid": self.annotation_set_uuid,
            "instances": list(self.instances),
            "legacy_geometry": self.legacy_geometry,
        }


@dataclass(frozen=True)
class WorkbenchPanelDTO:
    task_uuid: str
    disease_id: int
    disease_name: str
    target_level: str
    scope_id: int | None
    image_position: int | None
    editable: bool
    unavailable_reason: str | None
    media: WorkbenchMediaDTO | None
    evidence: tuple[WorkbenchMediaDTO, ...]
    grades: tuple[WorkbenchGradeOptionDTO, ...]
    annotation: WorkbenchAnnotationDTO
    existing_grade: dict[str, Any] | None
    task_state: str
    fields: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_uuid": self.task_uuid,
            "disease_id": self.disease_id,
            "disease_name": self.disease_name,
            "target_level": self.target_level,
            "scope_id": self.scope_id,
            "image_position": self.image_position,
            "editable": self.editable,
            "unavailable_reason": self.unavailable_reason,
            "media": self.media.to_dict() if self.media else None,
            "evidence": [item.to_dict() for item in self.evidence],
            "grades": [item.to_dict() for item in self.grades],
            "annotation": self.annotation.to_dict(),
            "existing_grade": self.existing_grade,
            "task_state": self.task_state,
            "fields": self.fields,
        }


@dataclass(frozen=True)
class WorkbenchSourceDTO:
    source_type: str
    profile_id: int | None
    profile_lineage: str
    project_id: int | None
    lab_unit_id: int
    profile: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorkbenchDTO:
    lease: WorkbenchLeaseDTO
    configuration_fingerprint: str
    source: WorkbenchSourceDTO
    panels: tuple[WorkbenchPanelDTO, ...]
    allowed_actions: tuple[str, ...]
    workflow_config: dict[str, Any] = field(default_factory=dict)
    schema_version: int = WORKBENCH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "configuration_fingerprint": self.configuration_fingerprint,
            "lease": self.lease.to_dict(),
            "source": asdict(self.source),
            "panels": [item.to_dict() for item in self.panels],
            "allowed_actions": list(self.allowed_actions),
            "workflow_config": self.workflow_config,
        }


@dataclass(frozen=True)
class AnnotationInstanceInputDTO:
    instance_uuid: str | None
    image_uuid: str
    class_source: str
    grading_feature_id: int | None
    project_class_id: int | None
    project_class_key: str | None
    geometry_type: str
    geometry: dict[str, Any]
    mask_tiles: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class GradeObservationDTO:
    task_uuid: str
    disease_grading_id: int
    comment: str | None
    selected_feature_ids: tuple[int, ...]
    selected_features_json: str | None
    feature_geometry_json: dict[str, Any] | None
    annotation_policy_revision: int
    annotation_instances: tuple[AnnotationInstanceInputDTO, ...]
    explicit_geometry_clear: bool
