"""Persistence ports consumed by authorization services."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role


@dataclass(frozen=True)
class GrantRecord:
    grant_id: int
    user_id: int
    role: Role
    scope: ScopeDTO
    active: bool


Q = TypeVar("Q")


class AuthorizationRepository(Protocol):
    def principal(self, user_id: int) -> PrincipalDTO | None: ...
    def grants_for(self, user_id: int) -> Sequence[GrantRecord]: ...


class ScopedQueryAdapter(Protocol[Q]):
    def apply(self, query: Q, grants: Sequence[GrantRecord]) -> Q: ...
