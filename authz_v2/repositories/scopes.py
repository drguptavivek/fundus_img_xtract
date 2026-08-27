"""Reusable scope-set projection for exact checks and SQL adapters."""

from __future__ import annotations

from authz_v2.core.resources import ScopeSetDTO
from authz_v2.repositories.contracts import GrantRecord


def scopes_from_grants(grants: tuple[GrantRecord, ...]) -> ScopeSetDTO:
    return ScopeSetDTO(frozenset(grant.scope for grant in grants if grant.active))
