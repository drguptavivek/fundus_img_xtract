"""SQL list authorization using the same grants consumed by exact checks."""

from __future__ import annotations

from authz_v2.core.actions import Action, action_from_name
from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.expressions import (
    ActivePrincipalRequirement,
    AnyRoleRequirement,
    BooleanFact,
    BooleanRequirement,
    Expression,
    IdentifierReleaseRequirement,
    ScopedRoleRequirement,
    ScopeRequirement,
)
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import DisclosureClass
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.services.decision import AuthorizationDecisionService


def _scope_query_safe(value, *, identifier_release: bool) -> bool:
    """Whether a query scoper can enforce every condition in one path."""
    if isinstance(value, Expression):
        return bool(value.requirements) and all(
            _scope_query_safe(child, identifier_release=identifier_release)
            for child in value.requirements
        )
    if isinstance(
        value,
        (
            ActivePrincipalRequirement,
            AnyRoleRequirement,
            ScopeRequirement,
            ScopedRoleRequirement,
        ),
    ):
        return True
    if isinstance(value, IdentifierReleaseRequirement):
        return not identifier_release
    return (
        isinstance(value, BooleanRequirement)
        and value.fact is BooleanFact.EXACT_RESOURCE
    )


def supports_scope_only_query(action: Action) -> bool:
    """Reject list operations whose exact policy needs row-specific evidence."""
    definition = CATALOGUE[action]
    return all(
        _scope_query_safe(
            expression,
            identifier_release=definition.disclosure_class
            is DisclosureClass.IDENTIFIER_RELEASE,
        )
        for _path_name, expression in definition.authorization_paths
    )


def applicable_grants(action: Action, grants):
    """Keep only grants that can satisfy a complete scoped-role requirement."""
    requirements: list[ScopedRoleRequirement | AnyRoleRequirement] = []

    def collect(value) -> None:
        if isinstance(value, (ScopedRoleRequirement, AnyRoleRequirement)):
            requirements.append(value)
        elif isinstance(value, Expression):
            for child in value.requirements:
                collect(child)

    for _path_name, expression in CATALOGUE[action].authorization_paths:
        collect(expression)
    return tuple(
        grant
        for grant in grants
        if any(
            grant.role in requirement.roles
            and (
                not isinstance(requirement, ScopedRoleRequirement)
                or grant.scope.scope_type.value != "system"
                or requirement.allow_system
            )
            for requirement in requirements
        )
    )


def filter_query(
    db,
    principal: PrincipalDTO,
    action: str | Action,
    resource_adapter,
    query,
    *,
    decision_service: AuthorizationDecisionService,
):
    """Apply a registered resource adapter's SQL predicate; deny unsupported inputs."""
    try:
        canonical = action_from_name(action)
    except ValueError as exc:
        raise AuthorizationError(DenialCode.UNKNOWN_ACTION) from exc
    definition = CATALOGUE[canonical]
    if resource_adapter.resource_type != definition.resource_type:
        raise AuthorizationError(DenialCode.UNKNOWN_RESOURCE)
    registered = decision_service.resources.get(resource_adapter.resource_type)
    if registered is not resource_adapter:
        raise AuthorizationError(DenialCode.UNKNOWN_RESOURCE)
    if not supports_scope_only_query(canonical):
        raise AuthorizationError(DenialCode.UNSUPPORTED_QUERY)
    grants = applicable_grants(canonical, decision_service.active_grants(principal))
    return resource_adapter.query_scoper(db, principal, canonical, grants, query)
