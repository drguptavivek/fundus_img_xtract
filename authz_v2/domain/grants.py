"""Typed grant lifecycle contracts and target-shape validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType, role_accepts_scope


class _DescriptionUnset:
    __slots__ = ()


DESCRIPTION_UNSET = _DescriptionUnset()


@dataclass(frozen=True)
class GrantCreateDTO:
    user_id: int
    role: Role
    scope: ScopeDTO
    description: str | None = None


@dataclass(frozen=True)
class GrantUpdateDTO:
    description: str | None | _DescriptionUnset = DESCRIPTION_UNSET
    active: bool | None = None


@dataclass(frozen=True)
class GrantViewDTO:
    id: int
    user_id: int
    role: Role
    scope: ScopeDTO
    description: str | None
    active: bool
    created_by_user_id: int | None
    updated_by_user_id: int | None
    deactivated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None


def normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 500:
        raise ValueError("grant description exceeds 500 characters")
    return normalized


def validate_grant_target(role: Role, scope: ScopeDTO) -> None:
    """Reject malformed or illegal scope targets before persistence."""
    if not role_accepts_scope(role, scope.scope_type):
        raise ValueError(
            f"{role.value} cannot be granted at {scope.scope_type.value} scope"
        )
    expected = {
        ScopeType.SYSTEM: (None, None, None, None, None),
        ScopeType.HOSPITAL: (scope.scope_id, None, None, None, None),
        ScopeType.LAB_UNIT: (scope.hospital_id, scope.scope_id, None, None, None),
        ScopeType.PROJECT: (None, None, scope.scope_id, None, None),
        ScopeType.PROJECT_LAB_UNIT: (
            scope.hospital_id,
            scope.lab_unit_id,
            scope.project_id,
            scope.scope_id,
            scope.project_lab_unit_id,
        ),
    }[scope.scope_type]
    (
        hospital_id,
        lab_unit_id,
        project_id,
        project_lab_unit_id,
        canonical_project_lab_id,
    ) = expected
    if scope.scope_type is ScopeType.SYSTEM:
        valid = scope.scope_id is None and all(
            value is None
            for value in (
                scope.hospital_id,
                scope.lab_unit_id,
                scope.project_id,
                scope.project_lab_unit_id,
            )
        )
    elif scope.scope_type is ScopeType.HOSPITAL:
        valid = hospital_id is not None and scope.hospital_id in {None, hospital_id}
    elif scope.scope_type is ScopeType.LAB_UNIT:
        valid = lab_unit_id is not None and hospital_id is not None
    elif scope.scope_type is ScopeType.PROJECT:
        valid = project_id is not None and scope.project_id in {None, project_id}
    else:
        valid = (
            project_lab_unit_id is not None
            and canonical_project_lab_id == project_lab_unit_id
            and project_id is not None
            and lab_unit_id is not None
        )
    if not valid:
        raise ValueError(f"invalid {scope.scope_type.value} grant target")
