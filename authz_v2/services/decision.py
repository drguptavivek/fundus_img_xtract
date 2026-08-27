"""Exact authorization orchestration over server-resolved resources."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

from authz_v2.core.actions import Action, action_from_name
from authz_v2.core.catalogue import CATALOGUE, check_action
from authz_v2.core.decisions import AuthorizationReceiptDTO, DecisionDTO
from authz_v2.core.expressions import BooleanFact
from authz_v2.core.principals import (
    EvaluationFactsDTO,
    GrantSource,
    PrincipalDTO,
    RoleGrantDTO,
)
from authz_v2.core.resources import ScopeSetDTO
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.repositories.contracts import AuthorizationRepository, GrantRecord
from authz_v2.resources.registry import ResourceRegistry, ResourceTarget
from authz_v2.telemetry.metrics import increment, observe_decision_duration


def _record_decision_metrics(decision: DecisionDTO, elapsed: float) -> None:
    """Best-effort telemetry must never alter an authorization result."""
    try:
        try:
            action = action_from_name(decision.action).value
        except ValueError:
            action = "unknown"
        outcome = "allow" if decision.allowed else "deny"
        increment("authz_decisions_total", action=action, outcome=outcome)
        if decision.allowed and decision.policy_path == "admin_break_glass":
            increment("authz_break_glass_total", action=action)
        observe_decision_duration(action, elapsed)
    except Exception:  # noqa: BLE001 - telemetry cannot control authorization
        # Metrics are operational signals, never part of the decision boundary.
        return


class AuthorizationDecisionService:
    """Resolve authoritative facts, then evaluate one canonical action."""

    def __init__(
        self, repository: AuthorizationRepository, resources: ResourceRegistry
    ) -> None:
        self.repository = repository
        self.resources = resources

    def check(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        resource: object | None,
    ) -> DecisionDTO:
        decision, _target = self._evaluate_with_metrics(db, principal, action, resource)
        return decision

    def _evaluate_with_metrics(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        resource: object | None,
    ) -> tuple[DecisionDTO, ResourceTarget | None]:
        started = perf_counter()
        try:
            result = self._evaluate(db, principal, action, resource)
        except Exception:
            try:
                canonical = action_from_name(action).value
            except ValueError:
                canonical = "unknown"
            _record_decision_metrics(
                DecisionDTO(False, canonical, "evaluation_error"),
                perf_counter() - started,
            )
            raise
        _record_decision_metrics(result[0], perf_counter() - started)
        return result

    def _evaluate(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        resource: object | None,
    ) -> tuple[DecisionDTO, ResourceTarget | None]:
        try:
            canonical = action_from_name(action)
        except ValueError:
            return DecisionDTO(
                False, str(action), DenialCode.UNKNOWN_ACTION.value
            ), None

        definition = CATALOGUE[canonical]
        authoritative = self._principal(
            principal, definition.authorization_paths[0][0] == "public"
        )
        if authoritative is None:
            return DecisionDTO(
                False, canonical.value, DenialCode.INACTIVE_PRINCIPAL.value
            ), None

        grants = self._grants(authoritative)
        target: ResourceTarget | None = None
        if definition.requires_resource:
            adapter = self.resources.get(definition.resource_type)
            if adapter is None:
                return DecisionDTO(
                    False, canonical.value, DenialCode.UNKNOWN_RESOURCE.value
                ), None
            target = adapter.resolver(db, resource)
            if target is None or not target.context.resolved:
                return DecisionDTO(
                    False, canonical.value, DenialCode.UNRESOLVED_RESOURCE.value
                ), None
            if not target.context.has_stable_identity():
                return DecisionDTO(
                    False, canonical.value, DenialCode.UNRESOLVED_RESOURCE.value
                ), None
            if target.context.scope is None:
                return DecisionDTO(
                    False, canonical.value, DenialCode.MISSING_SCOPE.value
                ), None
            # Disclosure is an action property, not caller input or adapter
            # discretion. This makes identifier-release authority additive at
            # runtime exactly as it is in the catalogue truth tables.
            target = replace(
                target,
                context=replace(
                    target.context,
                    disclosure_class=definition.disclosure_class,
                ),
            )

        facts = EvaluationFactsDTO(
            principal=authoritative,
            session=authoritative.session,
            resource=target.context if target else None,
            active_roles=frozenset(grant.role for grant in grants),
            role_grants=tuple(
                RoleGrantDTO(grant.grant_id, grant.role, grant.scope)
                for grant in grants
            ),
            grant_sources=(
                frozenset({GrantSource.AUTHORIZATION_GRANT}) if grants else frozenset()
            ),
            grant_ids=tuple(grant.grant_id for grant in grants),
            reachable_scopes=ScopeSetDTO(frozenset(grant.scope for grant in grants)),
            exact_resource=target is not None,
            self_identity=bool(
                target
                and authoritative.user_id is not None
                and (
                    target.context.owner_id == authoritative.user_id
                    or (
                        target.context.resource_type == "user"
                        and target.context.resource_id == authoritative.user_id
                    )
                )
            ),
        )
        if target is not None:
            protected_boolean_facts = {
                BooleanFact.EXACT_RESOURCE,
                BooleanFact.SELF_IDENTITY,
            }
            state_facts = {
                key: value
                for key, value in target.context.state.items()
                if key in {fact.value for fact in BooleanFact}
                and key not in {fact.value for fact in protected_boolean_facts}
                and isinstance(value, bool)
            }
            if state_facts:
                facts = replace(facts, **state_facts)
            adapter = self.resources.require(definition.resource_type)
            if adapter.facts_provider is not None:
                provided = adapter.facts_provider(
                    db, authoritative, canonical, target, facts
                )
                protected = (
                    "principal",
                    "session",
                    "resource",
                    "active_roles",
                    "role_grants",
                    "grant_ids",
                    "reachable_scopes",
                    "exact_resource",
                    "self_identity",
                )
                if any(
                    getattr(provided, key) != getattr(facts, key) for key in protected
                ):
                    return DecisionDTO(
                        False, canonical.value, DenialCode.INVALID_FACTS.value
                    ), target
                dynamic = {
                    item.value: getattr(provided, item.value)
                    for item in BooleanFact
                    if item not in protected_boolean_facts
                }
                relationships = tuple(provided.relationships)
                facts = replace(
                    facts,
                    **dynamic,
                    relationships=relationships,
                    grant_sources=(
                        (
                            frozenset({GrantSource.AUTHORIZATION_GRANT})
                            if grants
                            else frozenset()
                        )
                        | frozenset(
                            evidence.relationship
                            for evidence in relationships
                            if evidence.active
                        )
                    ),
                )

        return (
            check_action(
                canonical,
                facts,
                resource_type=target.context.resource_type if target else None,
                resource_resolved=target is not None
                or not definition.requires_resource,
            ),
            target,
        )

    def require(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        resource: object | None,
    ) -> AuthorizationReceiptDTO:
        decision, target = self._evaluate_with_metrics(db, principal, action, resource)
        if not decision.allowed or decision.policy_path is None:
            try:
                code = DenialCode(decision.reason_code)
            except ValueError:
                code = DenialCode.NOT_AUTHORIZED
            raise AuthorizationError(code)

        canonical = action_from_name(action)
        definition = CATALOGUE[canonical]
        return AuthorizationReceiptDTO(
            action=canonical.value,
            resource_type=definition.resource_type,
            resource_id=target.context.resource_id if target else None,
            policy_path=decision.policy_path,
            grant_ids=tuple(
                item for item in decision.evidence if isinstance(item, int)
            ),
            break_glass=decision.policy_path == "admin_break_glass",
            request_id=principal.session.request_id if principal.session else None,
            evaluated_at=principal.session.evaluated_at
            if principal.session
            else datetime.now(UTC),
        )

    def active_grants(self, principal: PrincipalDTO) -> tuple[GrantRecord, ...]:
        authoritative = self._principal(principal, False)
        return self._grants(authoritative) if authoritative is not None else ()

    def authoritative_principal(self, principal: PrincipalDTO) -> PrincipalDTO:
        """Reload the current authenticated principal or deny closed."""
        authoritative = self._principal(principal, False)
        if authoritative is None:
            raise AuthorizationError(DenialCode.INACTIVE_PRINCIPAL)
        return authoritative

    def _principal(self, principal: PrincipalDTO, public: bool) -> PrincipalDTO | None:
        if public:
            return principal
        if principal.user_id is None or not principal.authenticated:
            return None
        current = self.repository.principal(principal.user_id)
        if current is None or not current.active or not current.authenticated:
            return None
        return replace(current, session=principal.session)

    def _grants(self, principal: PrincipalDTO) -> tuple[GrantRecord, ...]:
        if principal.user_id is None:
            return ()
        return tuple(
            grant
            for grant in self.repository.grants_for(principal.user_id)
            if grant.active
        )
