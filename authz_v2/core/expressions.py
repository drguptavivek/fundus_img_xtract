"""Typed authorization expression algebra. Unknown or malformed facts deny closed."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .principals import (
    EvaluationFactsDTO,
    GrantSource,
    RelationshipEvidenceDTO,
    SessionChannel,
)
from .resources import DisclosureClass
from .roles import Role


class Requirement(Protocol):
    def __call__(self, facts: EvaluationFactsDTO) -> bool: ...


class BooleanFact(StrEnum):
    EXACT_RESOURCE = "exact_resource"
    SELF_IDENTITY = "self_identity"
    OWNER_OR_PARTICIPANT = "owner_or_participant"
    CREDENTIAL_VALID = "credential_valid"
    UPLOAD_PROFILE_MATCHES = "upload_profile_matches"
    TARGET_ACTIVE = "target_active"
    GRADING_SLOT_MATCHES = "grading_slot_matches"
    ALLOCATION_ENFORCED = "allocation_enforced"
    ALLOCATION_MATCHES = "allocation_matches"
    DOMAIN_VALID = "domain_valid"
    AUTOMATION_RULE_MATCHES = "automation_rule_matches"
    AUTOMATION_TARGET_MATCHES = "automation_target_matches"


@dataclass(frozen=True)
class ActivePrincipalRequirement:
    authenticated: bool = True

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return facts.principal.active and (
            facts.principal.authenticated or not self.authenticated
        )


@dataclass(frozen=True)
class PublicRequirement:
    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return True


@dataclass(frozen=True)
class AnyRoleRequirement:
    roles: frozenset[Role]

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return bool(self.roles & facts.active_roles)


@dataclass(frozen=True)
class ScopedRoleRequirement:
    roles: frozenset[Role]
    allow_system: bool = False

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        if not facts.resource or not facts.resource.scope:
            return False
        return any(
            grant.role in self.roles
            and grant.scope.contains(
                facts.resource.scope, allow_system=self.allow_system
            )
            for grant in facts.role_grants
        )


@dataclass(frozen=True)
class GrantSourceRequirement:
    sources: frozenset[GrantSource]

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        if GrantSource.AUTHORIZATION_GRANT in self.sources and facts.role_grants:
            return True
        return any(
            evidence.active and evidence.relationship in self.sources
            for evidence in facts.relationships
        )


@dataclass(frozen=True)
class RelationshipRequirement:
    """Require one active relationship tied to this actor and exact resource."""

    source: GrantSource
    attributes: tuple[tuple[str, bool], ...] = ()
    require_subject: bool = True
    require_scope: bool = True

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        resource = facts.resource
        if resource is None:
            return False
        for evidence in facts.relationships:
            if not evidence.active or evidence.relationship is not self.source:
                continue
            if self.require_subject and evidence.subject_id != facts.principal.user_id:
                continue
            if (
                evidence.object_type != resource.resource_type
                or evidence.object_id != resource.resource_id
            ):
                continue
            if self.require_scope:
                if resource.scope is None or evidence.scope is None:
                    continue
                if not evidence.scope.contains(resource.scope, allow_system=False):
                    continue
            if any(
                evidence.attribute(key) is not value for key, value in self.attributes
            ):
                continue
            return True
        return False


@dataclass(frozen=True)
class SessionChannelRequirement:
    channels: frozenset[SessionChannel]

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return bool(facts.session and facts.session.channel in self.channels)


@dataclass(frozen=True)
class ScopeRequirement:
    allow_system: bool = False

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return facts.scope_reaches_resource(allow_system=self.allow_system)


@dataclass(frozen=True)
class BooleanRequirement:
    fact: BooleanFact
    expected: bool = True

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return getattr(facts, self.fact.value) is self.expected


@dataclass(frozen=True)
class IdentifierReleaseRequirement:
    """Identifier release is additive; it never replaces ordinary authority."""

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        if (
            not facts.resource
            or facts.resource.disclosure_class is not DisclosureClass.IDENTIFIER_RELEASE
        ):
            return True
        if not facts.resource.scope:
            return False
        return any(
            grant.role is Role.PII_EXPORTER
            and grant.scope.contains(facts.resource.scope, allow_system=False)
            for grant in facts.role_grants
        )


@dataclass(frozen=True)
class Expression:
    operator: str
    requirements: tuple[Requirement, ...]
    name: str

    def __call__(self, facts: EvaluationFactsDTO) -> bool:
        return evaluate(self, facts)


def all_of(*requirements: Requirement, name: str) -> Expression:
    return Expression("all_of", tuple(requirements), name)


def any_of(*requirements: Requirement, name: str) -> Expression:
    return Expression("any_of", tuple(requirements), name)


def evaluate(expression: Expression | Requirement, facts: EvaluationFactsDTO) -> bool:
    try:
        if isinstance(expression, Expression):
            if not expression.requirements:
                return False
            values = (evaluate(item, facts) for item in expression.requirements)
            if expression.operator == "all_of":
                return all(values)
            if expression.operator == "any_of":
                return any(values)
            return False
        return bool(expression(facts))
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def supporting_grant_ids(
    expression: Expression | Requirement, facts: EvaluationFactsDTO
) -> tuple[int, ...]:
    """Return only general grants that satisfy the selected expression branch."""
    if not evaluate(expression, facts):
        return ()
    if isinstance(expression, Expression):
        children = expression.requirements
        if expression.operator == "any_of":
            children = tuple(child for child in children if evaluate(child, facts))[:1]
        return tuple(
            dict.fromkeys(
                grant_id
                for child in children
                for grant_id in supporting_grant_ids(child, facts)
            )
        )
    if isinstance(expression, ScopedRoleRequirement):
        if not facts.resource or not facts.resource.scope:
            return ()
        return tuple(
            grant.grant_id
            for grant in facts.role_grants
            if grant.role in expression.roles
            and grant.scope.contains(
                facts.resource.scope, allow_system=expression.allow_system
            )
        )
    if isinstance(expression, AnyRoleRequirement):
        return tuple(
            grant.grant_id
            for grant in facts.role_grants
            if grant.role in expression.roles
        )
    if isinstance(expression, IdentifierReleaseRequirement):
        if (
            not facts.resource
            or facts.resource.disclosure_class is not DisclosureClass.IDENTIFIER_RELEASE
        ):
            return ()
        if not facts.resource.scope:
            return ()
        return tuple(
            grant.grant_id
            for grant in facts.role_grants
            if grant.role is Role.PII_EXPORTER
            and grant.scope.contains(facts.resource.scope, allow_system=False)
        )
    return ()


def supporting_relationships(
    expression: Expression | Requirement, facts: EvaluationFactsDTO
) -> tuple[RelationshipEvidenceDTO, ...]:
    """Return relationship rows used by the first satisfied expression branch."""
    if not evaluate(expression, facts):
        return ()
    if isinstance(expression, Expression):
        children = expression.requirements
        if expression.operator == "any_of":
            children = tuple(child for child in children if evaluate(child, facts))[:1]
        return tuple(
            dict.fromkeys(
                evidence
                for child in children
                for evidence in supporting_relationships(child, facts)
            )
        )
    if not isinstance(expression, RelationshipRequirement) or facts.resource is None:
        return ()
    return tuple(
        evidence
        for evidence in facts.relationships
        if evidence.active
        and evidence.relationship is expression.source
        and (
            not expression.require_subject
            or evidence.subject_id == facts.principal.user_id
        )
        and evidence.object_type == facts.resource.resource_type
        and evidence.object_id == facts.resource.resource_id
        and (
            not expression.require_scope
            or (
                facts.resource.scope is not None
                and evidence.scope is not None
                and evidence.scope.contains(facts.resource.scope, allow_system=False)
            )
        )
        and all(
            evidence.attribute(key) is value for key, value in expression.attributes
        )
    )[:1]


def active_principal() -> ActivePrincipalRequirement:
    return ActivePrincipalRequirement()


def public() -> PublicRequirement:
    return PublicRequirement()


def roles_any(*roles: Role) -> AnyRoleRequirement:
    return AnyRoleRequirement(frozenset(roles))


def scoped_roles(*roles: Role, allow_system: bool = False) -> ScopedRoleRequirement:
    return ScopedRoleRequirement(frozenset(roles), allow_system)


def grants_any(*sources: GrantSource) -> GrantSourceRequirement:
    return GrantSourceRequirement(frozenset(sources))


def relationship(
    source: GrantSource,
    *,
    attributes: tuple[tuple[str, bool], ...] = (),
    require_subject: bool = True,
    require_scope: bool = True,
) -> RelationshipRequirement:
    return RelationshipRequirement(
        source,
        attributes,
        require_subject=require_subject,
        require_scope=require_scope,
    )


def channels_any(*channels: SessionChannel) -> SessionChannelRequirement:
    return SessionChannelRequirement(frozenset(channels))


def scoped(*, allow_system: bool) -> ScopeRequirement:
    return ScopeRequirement(allow_system)


def fact(value: BooleanFact, expected: bool = True) -> BooleanRequirement:
    return BooleanRequirement(value, expected)
