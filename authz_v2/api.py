"""Narrow public Python facade for the unified authorization module."""

from __future__ import annotations

from authz_v2.core.actions import Action
from authz_v2.core.principals import PrincipalDTO
from authz_v2.domain.descriptions import describe_catalogue
from authz_v2.repositories.grants import GrantRepository
from authz_v2.resources.composition import register_core_adapters, register_core_choices
from authz_v2.resources.registry import choice_registry, registry
from authz_v2.services.choices import list_choices as _list_choices
from authz_v2.services.decision import AuthorizationDecisionService
from authz_v2.services.listing import filter_query as _filter_query


def _service(db) -> AuthorizationDecisionService:
    register_core_adapters(registry)
    register_core_choices(choice_registry)
    return AuthorizationDecisionService(GrantRepository(db), registry)


def check(
    db, principal: PrincipalDTO, action: str | Action, resource: object | None = None
):
    return _service(db).check(db, principal, action, resource)


def require(
    db, principal: PrincipalDTO, action: str | Action, resource: object | None = None
):
    return _service(db).require(db, principal, action, resource)


def filter_query(
    db, principal: PrincipalDTO, action: str | Action, resource_adapter, query
):
    return _filter_query(
        db,
        principal,
        action,
        resource_adapter,
        query,
        decision_service=_service(db),
    )


def list_choices(
    db,
    principal: PrincipalDTO,
    action: str | Action,
    choice_kind: str,
    filters: dict[str, object] | None = None,
):
    service = _service(db)
    return _list_choices(
        db,
        principal,
        action,
        choice_kind,
        filters,
        choices=choice_registry,
        decision_service=service,
    )


__all__ = ["check", "describe_catalogue", "filter_query", "list_choices", "require"]
