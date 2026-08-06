"""Typed contracts shared by grading-allocation services and APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from grading_allocation.constants import (
    AllocationCapacity,
    AllocationScope,
    task_family_for_scope,
)


@dataclass(frozen=True)
class TargetIdentity:
    scope: AllocationScope
    disease_id: int | None = None
    encounter_set_type_id: int | None = None

    @property
    def key(self) -> str:
        disease = self.disease_id if self.disease_id is not None else "all"
        encounter_set_type = self.encounter_set_type_id if self.encounter_set_type_id is not None else "none"
        return f"{self.scope.value}:{disease}:{encounter_set_type}"


@dataclass
class ProjectGradingTargetDTO:
    identity: TargetIdentity
    label: str
    disease_name: str | None = None
    encounter_set_type_name: str | None = None
    source_profiles: dict[int, str] = field(default_factory=dict)
    grading_scheme_ids: set[int] = field(default_factory=set)
    diseases: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.identity.key,
            "scope": self.identity.scope.value,
            "task_family": task_family_for_scope(self.identity.scope).value,
            "disease_id": self.identity.disease_id,
            "disease_name": self.disease_name,
            "encounter_set_type_id": self.identity.encounter_set_type_id,
            "encounter_set_type_name": self.encounter_set_type_name,
            "label": self.label,
            "grading_scheme_ids": sorted(self.grading_scheme_ids),
            "diseases": [
                {"id": disease_id, "name": name}
                for disease_id, name in sorted(
                    self.diseases.items(),
                    key=lambda item: (item[1].lower(), item[0]),
                )
            ],
            "source_profiles": [
                {"id": profile_id, "name": name}
                for profile_id, name in sorted(self.source_profiles.items())
            ],
        }


@dataclass(frozen=True)
class AllocationInputDTO:
    user_id: int
    lab_unit_id: int
    scope: AllocationScope
    capacity: AllocationCapacity
    disease_id: int | None = None
    encounter_set_type_id: int | None = None

    @property
    def target(self) -> TargetIdentity:
        return TargetIdentity(
            scope=self.scope,
            disease_id=self.disease_id,
            encounter_set_type_id=self.encounter_set_type_id,
        )


@dataclass(frozen=True)
class GraderCandidateDTO:
    user_id: int
    username: str
    full_name: str | None
    roles: tuple[str, ...]
    is_member_of_lab: bool

    def to_dict(self) -> dict:
        return {
            "id": self.user_id,
            "username": self.username,
            "full_name": self.full_name,
            "roles": list(self.roles),
            "is_member_of_lab": self.is_member_of_lab,
        }


@dataclass(frozen=True)
class TaskAllocationContext:
    task_id: int
    project_id: int | None
    lab_unit_id: int
    target: TargetIdentity | None
    source_project_ids: tuple[int, ...] = ()

    @property
    def is_project_scoped(self) -> bool:
        return self.project_id is not None


@dataclass(frozen=True)
class GraderAllocationDTO:
    id: int
    project_id: int
    user_id: int
    username: str | None
    user_full_name: str | None
    lab_unit_id: int
    lab_unit_name: str | None
    scope: str
    disease_id: int | None
    disease_name: str | None
    encounter_set_type_id: int | None
    encounter_set_type_name: str | None
    capacity: str
    active: bool
    created_at: datetime | None
    updated_at: datetime | None
    deactivated_at: datetime | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "user": {
                "id": self.user_id,
                "username": self.username,
                "full_name": self.user_full_name,
            },
            "lab_unit": {"id": self.lab_unit_id, "name": self.lab_unit_name},
            "scope": self.scope,
            "disease_id": self.disease_id,
            "disease_name": self.disease_name,
            "encounter_set_type_id": self.encounter_set_type_id,
            "encounter_set_type_name": self.encounter_set_type_name,
            "capacity": self.capacity,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deactivated_at": self.deactivated_at.isoformat() if self.deactivated_at else None,
        }


@dataclass(frozen=True)
class AllocationPolicyDTO:
    project_id: int
    enforcement_enabled: bool
    updated_at: datetime | None

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "enforcement_enabled": self.enforcement_enabled,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class ProjectAllocationStateDTO:
    project_id: int
    policy: AllocationPolicyDTO
    targets: tuple[dict, ...]
    allocations: tuple[GraderAllocationDTO, ...]
    warnings: tuple[dict[str, object], ...]

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "policy": self.policy.to_dict(),
            "targets": list(self.targets),
            "allocations": [allocation.to_dict() for allocation in self.allocations],
            "warnings": list(self.warnings),
        }
