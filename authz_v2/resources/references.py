"""Strict transport-reference validation for exact authorization targets."""

from __future__ import annotations

from dataclasses import dataclass

from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role


@dataclass(frozen=True)
class AutomationTargetRef:
    """Exact domain target paired with the stored rule that triggered it."""

    target: object
    automation_rule_id: int


@dataclass(frozen=True)
class UserCreationTargetRef:
    """Requested account scope and grants, supplied together or denied."""

    hospital_id: int
    requested_grants: tuple[tuple[Role, ScopeDTO], ...]


@dataclass(frozen=True)
class AdminMobileSessionTargetRef:
    """Bind an admin session mutation to both URL identifiers."""

    user_id: int
    session_id: str


@dataclass(frozen=True)
class SystemOperationRef:
    """Closed identifier for an exact system-maintenance mutation."""

    operation: str


@dataclass(frozen=True)
class ActiveConfigurationRef:
    """Resolve the single active configuration of a declared kind."""

    kind: str


@dataclass(frozen=True)
class LookupRecordRef:
    """Typed lookup identity; bare integers are intentionally ambiguous."""

    kind: str
    record_id: int


@dataclass(frozen=True)
class GradingConfigRef:
    """Typed identity for a persisted grading configuration record."""

    kind: str
    record_id: int


@dataclass(frozen=True)
class GradingSchemeGradeRef:
    """Grade identity bound to its grading-scheme path parent."""

    scheme_id: int
    grade_id: int


@dataclass(frozen=True)
class ExecutableConfigRef:
    """Typed identity for AI and scheduler configuration records."""

    kind: str
    record_id: int


@dataclass(frozen=True)
class GradingRepairBatchRef:
    """Bounded exact set of grading tasks selected for one repair."""

    task_ids: tuple[int, ...]


@dataclass(frozen=True)
class S3SyncQueryRef:
    """Exact hospital boundary required for an S3 sync listing."""

    hospital_id: int


@dataclass(frozen=True)
class TaskBackfillTargetRef:
    """Complete, bounded backfill scope supplied by the caller."""

    hospital_id: int
    lab_unit_ids: tuple[int, ...]


@dataclass(frozen=True)
class RemidioConfigRef:
    """Typed identity for one persisted Remidio integration record."""

    kind: str
    record_id: int


@dataclass(frozen=True)
class RemidioProjectSyncRef:
    """Project plus the complete active Lab Unit set selected for sync."""

    project_id: int
    lab_unit_ids: tuple[int, ...]


@dataclass(frozen=True)
class WorkbenchSessionRef:
    """Workbench lease identity and optional current bearer credential."""

    session_uuid: str
    raw_token: str | None = None
    token_generation: int | None = None


@dataclass(frozen=True)
class WorkbenchAcquisitionRef:
    """Complete target-selection facts for acquiring a grading lease."""

    kind: str
    identifier: int | str | None
    role_slot: str | None
    disease_ids: tuple[int, ...] = ()
    lab_unit_id: int | None = None


@dataclass(frozen=True)
class RemoteInferenceBatchRef:
    """Bounded project encounter set selected for one inference job."""

    project_id: int
    encounter_ids: tuple[int, ...]


@dataclass(frozen=True)
class JobTokenRef:
    """Disambiguated external token for one persisted job."""

    token: str


@dataclass(frozen=True)
class ProjectAllocationTargetRef:
    """Existing allocation or proposed project-site/user allocation target."""

    project_id: int
    allocation_id: int | None = None
    lab_unit_id: int | None = None
    user_id: int | None = None


@dataclass(frozen=True)
class UploadLabUnitRef:
    """Lab Unit option in either classical or explicit project context."""

    lab_unit_id: int
    project_id: int | None = None


@dataclass(frozen=True)
class DirectImageUuidRef:
    """Opaque UUID identity for one persisted direct-image upload."""

    uuid: str


def is_positive_int(value: object) -> bool:
    """Accept database identifiers, never booleans, zero, or negative values."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def is_stable_resource_id(value: object) -> bool:
    """Accept a positive integer or a non-empty bounded opaque identifier."""
    if is_positive_int(value):
        return True
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= 255
        and not any(character.isspace() for character in value)
    )
