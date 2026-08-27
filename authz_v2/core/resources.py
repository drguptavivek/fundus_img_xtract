"""Resource and scope contracts with explicit classical/project separation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from .roles import ScopeType


class DisclosureClass(StrEnum):
    MASKED = "masked"
    IDENTIFIER_IN_PLACE = "identifier_in_place"
    IDENTIFIER_RELEASE = "identifier_release"


@dataclass(frozen=True)
class ScopeDTO:
    scope_type: ScopeType
    scope_id: int | None = None
    hospital_id: int | None = None
    lab_unit_id: int | None = None
    project_id: int | None = None
    project_lab_unit_id: int | None = None

    def contains(self, other: ScopeDTO, *, allow_system: bool = False) -> bool:
        """Return containment without ever crossing classical/project ownership."""
        if self.scope_type is ScopeType.SYSTEM:
            return allow_system
        if self.scope_type is ScopeType.HOSPITAL:
            return (
                other.project_id is None
                and other.project_lab_unit_id is None
                and self.scope_id is not None
                and self.scope_id
                == (
                    other.scope_id
                    if other.scope_type is ScopeType.HOSPITAL
                    else other.hospital_id
                )
            )
        if self.scope_type is ScopeType.LAB_UNIT:
            return (
                other.project_id is None
                and other.project_lab_unit_id is None
                and self.scope_id is not None
                and self.scope_id
                == (
                    other.scope_id
                    if other.scope_type is ScopeType.LAB_UNIT
                    else other.lab_unit_id
                )
            )
        if self.scope_type is ScopeType.PROJECT:
            return self.scope_id is not None and self.scope_id == (
                other.scope_id
                if other.scope_type is ScopeType.PROJECT
                else other.project_id
            )
        if self.scope_type is ScopeType.PROJECT_LAB_UNIT:
            return self.scope_id is not None and self.scope_id == (
                other.scope_id
                if other.scope_type is ScopeType.PROJECT_LAB_UNIT
                else other.project_lab_unit_id
            )
        return False


@dataclass(frozen=True)
class ScopeSetDTO:
    scopes: frozenset[ScopeDTO] = field(default_factory=frozenset)

    def reaches(self, scope: ScopeDTO, *, allow_system: bool = False) -> bool:
        return any(
            candidate.contains(scope, allow_system=allow_system)
            for candidate in self.scopes
        )


@dataclass(frozen=True)
class ResourceContextDTO:
    resource_type: str
    resource_id: int | str | None
    scope: ScopeDTO | None
    owner_id: int | None = None
    requester_id: int | None = None
    disclosure_class: DisclosureClass = DisclosureClass.MASKED
    state: Mapping[str, bool | int | str | None] = field(default_factory=dict)
    resolved: bool = True

    def has_stable_identity(self) -> bool:
        value = self.resource_id
        if isinstance(value, bool) or value is None:
            return False
        if isinstance(value, int):
            return value > 0
        return (
            isinstance(value, str)
            and value == value.strip()
            and 0 < len(value) <= 255
            and not any(character.isspace() for character in value)
        )
