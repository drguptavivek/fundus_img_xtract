"""Typed contracts for project role-scope grants."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRoleGrantInput:
    """Validated transport-independent input for one project role grant."""

    project_id: int
    user_id: int
    role_name: str
    scope_type: str
    lab_unit_id: int | None = None
    active: bool = True


@dataclass(frozen=True)
class ProjectRoleGrantDTO:
    """Detached project role grant returned to APIs and templates."""

    id: int
    project_id: int
    user_id: int
    username: str
    user_name: str
    role_name: str
    scope_type: str
    hospital_id: int | None
    hospital_name: str | None
    lab_unit_id: int | None
    lab_unit_name: str | None
    active: bool
