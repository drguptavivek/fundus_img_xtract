"""Authorized server-side choice-list projections."""

from __future__ import annotations

from authz_v2.core.actions import Action, action_from_name
from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.choices import ChoiceListDTO
from authz_v2.core.principals import PrincipalDTO
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.resources.registry import ChoiceRegistry
from authz_v2.services.decision import AuthorizationDecisionService
from authz_v2.services.listing import applicable_grants


def list_choices(
    db,
    principal: PrincipalDTO,
    action: str | Action,
    choice_kind: str,
    filters: dict[str, object] | None = None,
    *,
    choices: ChoiceRegistry,
    decision_service: AuthorizationDecisionService,
) -> ChoiceListDTO:
    """Return choices from a registered provider; an unknown kind denies closed."""
    try:
        canonical = action_from_name(action)
    except ValueError as exc:
        raise AuthorizationError(DenialCode.UNKNOWN_ACTION) from exc
    registration = choices.get(choice_kind)
    if registration is None:
        raise AuthorizationError(DenialCode.UNKNOWN_RESOURCE)
    if registration.action is not canonical:
        raise AuthorizationError(DenialCode.NOT_AUTHORIZED)
    authoritative = decision_service.authoritative_principal(principal)
    definition = CATALOGUE[canonical]
    all_grants = decision_service.active_grants(authoritative)
    if definition.requires_resource:
        if definition.resource_type != "user" or authoritative.user_id is None:
            raise AuthorizationError(DenialCode.UNSUPPORTED_QUERY)
        decision_service.require(db, authoritative, canonical, authoritative.user_id)
        grants = all_grants
    else:
        grants = applicable_grants(canonical, all_grants)
        if not grants:
            raise AuthorizationError(DenialCode.NOT_AUTHORIZED)
    return registration.provider(
        db, authoritative, canonical, grants, dict(filters or {})
    )
