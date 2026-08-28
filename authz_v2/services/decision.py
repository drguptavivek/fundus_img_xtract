"""Exact authorization orchestration over server-resolved resources."""

from __future__ import annotations

from collections.abc import Callable
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
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import ScopeSetDTO
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.repositories.contracts import AuthorizationRepository, GrantRecord
from authz_v2.resources.registry import ResourceRegistry, ResourceTarget
from authz_v2.resources.references import ResourceSetRef
from authz_v2.telemetry.events import AuthorizationEvent
from authz_v2.telemetry.logging import emit_authorization_event
from authz_v2.telemetry.metrics import increment, observe_decision_duration

SessionAttestor = Callable[[object, PrincipalDTO, SessionContextDTO], bool]


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
        self,
        repository: AuthorizationRepository,
        resources: ResourceRegistry,
        *,
        session_attestor: SessionAttestor | None = None,
        event_emitter: Callable[[AuthorizationEvent], None] = emit_authorization_event,
    ) -> None:
        self.repository = repository
        self.resources = resources
        self.session_attestor = session_attestor
        self.event_emitter = event_emitter

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
            self._emit_event(principal, canonical, "error", None, False, started)
            raise
        _record_decision_metrics(result[0], perf_counter() - started)
        self._emit_event(
            principal,
            result[0].action,
            "allow" if result[0].allowed else "deny",
            result[0].policy_path,
            result[0].policy_path == "admin_break_glass",
            started,
        )
        return result

    def _emit_event(
        self, principal, action, outcome, policy_path, break_glass, started
    ) -> None:
        try:
            session = principal.session
            self.event_emitter(
                AuthorizationEvent(
                    event="authorization_decision",
                    request_id=session.request_id if session else None,
                    actor_id=principal.user_id,
                    session_kind=session.channel.value if session else "unknown",
                    endpoint="",
                    action=action,
                    outcome=outcome,
                    policy_path=policy_path,
                    break_glass=break_glass,
                    duration_ms=(perf_counter() - started) * 1000,
                )
            )
        except Exception:  # noqa: BLE001 - operational telemetry is best effort
            return

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
        signed_only = all(
            path_name == "signed_credential"
            for path_name, _expression in definition.authorization_paths
        )
        authoritative = self._principal(
            db,
            principal,
            definition.authorization_paths[0][0] == "public",
            signed=signed_only,
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

        decision = check_action(
            canonical,
            facts,
            resource_type=target.context.resource_type if target else None,
            resource_resolved=target is not None or not definition.requires_resource,
        )
        return decision, target

    def require(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        resource: object | None,
        *,
        audit_service=None,
    ) -> AuthorizationReceiptDTO | tuple[AuthorizationReceiptDTO, ...]:
        if isinstance(resource, ResourceSetRef):
            return self.require_all(
                db,
                principal,
                action,
                resource,
                audit_service=audit_service,
            )
        decision, target = self._evaluate_with_metrics(db, principal, action, resource)
        if not decision.allowed or decision.policy_path is None:
            try:
                code = DenialCode(decision.reason_code)
            except ValueError:
                code = DenialCode.NOT_AUTHORIZED
            raise AuthorizationError(code)

        return self._receipt_for_allowed(
            db,
            principal,
            action,
            decision,
            target,
            audit_service=audit_service,
        )

    def _receipt_for_allowed(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        decision: DecisionDTO,
        target: ResourceTarget | None,
        *,
        audit_service=None,
    ) -> AuthorizationReceiptDTO:
        """Build and durably audit a previously allowed exact decision."""

        canonical = action_from_name(action)
        definition = CATALOGUE[canonical]
        receipt = AuthorizationReceiptDTO(
            action=canonical.value,
            resource_type=definition.resource_type,
            resource_id=target.context.resource_id if target else None,
            policy_path=decision.policy_path,
            grant_ids=tuple(
                item for item in decision.evidence if isinstance(item, int)
            ),
            scope=target.context.scope if target else None,
            relationship_evidence=decision.relationship_evidence,
            break_glass=decision.policy_path == "admin_break_glass",
            request_id=principal.session.request_id if principal.session else None,
            evaluated_at=principal.session.evaluated_at
            if principal.session
            else datetime.now(UTC),
        )
        if definition.audit_required or receipt.break_glass:
            if audit_service is None:
                raise AuthorizationError(DenialCode.AUDIT_REQUIRED)
            authoritative = self._principal(
                db,
                principal,
                False,
                signed=all(
                    path_name == "signed_credential"
                    for path_name, _expression in definition.authorization_paths
                ),
            )
            if authoritative is None:
                raise AuthorizationError(DenialCode.INVALID_SESSION)
            audit_service.record_allowed(
                event="authorization_allow",
                principal=authoritative,
                receipt=receipt,
                resource=target.context if target else None,
            )
        return receipt

    def require_all(
        self,
        db,
        principal: PrincipalDTO,
        action: str | Action,
        resources: ResourceSetRef,
        *,
        audit_service=None,
    ) -> tuple[AuthorizationReceiptDTO, ...]:
        """Require one action for every distinct member of a bounded exact set."""
        if not isinstance(resources, ResourceSetRef):
            raise AuthorizationError(DenialCode.UNRESOLVED_RESOURCE)
        members = resources.members
        if not 0 < len(members) <= 500:
            raise AuthorizationError(DenialCode.UNRESOLVED_RESOURCE)

        evaluated: list[tuple[DecisionDTO, ResourceTarget]] = []
        identities: set[tuple[str, int | str]] = set()
        for member in members:
            decision, target = self._evaluate_with_metrics(
                db, principal, action, member
            )
            if (
                not decision.allowed
                or decision.policy_path is None
                or target is None
            ):
                try:
                    code = DenialCode(decision.reason_code)
                except ValueError:
                    code = DenialCode.NOT_AUTHORIZED
                raise AuthorizationError(code)
            identity = (target.context.resource_type, target.context.resource_id)
            if identity in identities:
                raise AuthorizationError(DenialCode.UNRESOLVED_RESOURCE)
            identities.add(identity)
            evaluated.append((decision, target))

        return tuple(
            self._receipt_for_allowed(
                db,
                principal,
                action,
                decision,
                target,
                audit_service=audit_service,
            )
            for decision, target in evaluated
        )

    def require_audited(
        self, db, principal, action, resource, *, audit_service
    ) -> AuthorizationReceiptDTO:
        return self.require(
            db,
            principal,
            action,
            resource,
            audit_service=audit_service,
        )

    def active_grants(
        self, principal: PrincipalDTO, *, db=None
    ) -> tuple[GrantRecord, ...]:
        authoritative = self._principal(db, principal, False)
        return self._grants(authoritative) if authoritative is not None else ()

    def authoritative_principal(
        self, principal: PrincipalDTO, *, db=None
    ) -> PrincipalDTO:
        """Reload the current authenticated principal or deny closed."""
        authoritative = self._principal(db, principal, False)
        if authoritative is None:
            raise AuthorizationError(DenialCode.INACTIVE_PRINCIPAL)
        return authoritative

    def _principal(
        self, db, principal: PrincipalDTO, public: bool, *, signed: bool = False
    ) -> PrincipalDTO | None:
        if public:
            return principal
        session = principal.session
        if signed:
            if (
                session is None
                or session.channel is not SessionChannel.SIGNED
                or session.credential_id is None
                or not session.credential_proof
            ):
                return None
            return PrincipalDTO(
                None,
                True,
                False,
                replace(session, evaluated_at=datetime.now(UTC)),
            )
        if principal.user_id is None or not principal.authenticated:
            return None
        current = self.repository.principal(principal.user_id)
        if current is None or not current.active or not current.authenticated:
            return None
        session = principal.session
        if (
            session is not None
            and session.channel in {SessionChannel.MOBILE, SessionChannel.AUTOMATION}
            and (
                self.session_attestor is None
                or not self.session_attestor(db, current, session)
            )
        ):
            return None
        return replace(
            current,
            session=(
                replace(session, evaluated_at=datetime.now(UTC)) if session else None
            ),
        )

    def _grants(self, principal: PrincipalDTO) -> tuple[GrantRecord, ...]:
        if principal.user_id is None:
            return ()
        return tuple(
            grant
            for grant in self.repository.grants_for(principal.user_id)
            if grant.active
        )
