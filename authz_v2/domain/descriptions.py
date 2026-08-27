"""Human-readable projections generated from the executable catalogue."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass

from authz_v2.core.actions import ACTION_MANIFEST, Action
from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.expressions import Expression
from authz_v2.core.roles import ROLE_CONTRACTS


@dataclass(frozen=True)
class AccessPathDescriptionDTO:
    name: str
    requirements: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionDescriptionDTO:
    action: str
    label: str
    description: str
    resource_type: str
    paths: tuple[AccessPathDescriptionDTO, ...]
    disclosure_class: str
    break_glass: str
    audit_mode: str


@dataclass(frozen=True)
class RoleDescriptionDTO:
    role: str
    label: str
    purpose: str
    permitted_scope_types: frozenset[str]


@dataclass(frozen=True)
class AuthorizationCatalogueDTO:
    actions: tuple[ActionDescriptionDTO, ...]
    roles: tuple[RoleDescriptionDTO, ...]


def _requirement_names(value: object) -> tuple[str, ...]:
    if isinstance(value, Expression):
        names: list[str] = []
        for requirement in value.requirements:
            names.extend(_requirement_names(requirement))
        return tuple(names)
    name = type(value).__name__
    if not is_dataclass(value):
        return (name,)
    details = []
    for item in fields(value):
        rendered = getattr(value, item.name)
        if isinstance(rendered, frozenset):
            rendered = ",".join(
                sorted(getattr(member, "value", str(member)) for member in rendered)
            )
        else:
            rendered = getattr(rendered, "value", rendered)
        details.append(f"{item.name}={rendered}")
    return (f"{name}({'; '.join(details)})",)


def describe_catalogue(filters: set[str] | None = None) -> AuthorizationCatalogueDTO:
    names = sorted(ACTION_MANIFEST & filters) if filters else sorted(ACTION_MANIFEST)
    actions = []
    for name in names:
        definition = CATALOGUE[Action(name)]
        actions.append(
            ActionDescriptionDTO(
                action=name,
                label=definition.label,
                description=definition.description,
                resource_type=definition.resource_type,
                paths=tuple(
                    AccessPathDescriptionDTO(path_name, _requirement_names(expression))
                    for path_name, expression in definition.authorization_paths
                ),
                disclosure_class=definition.disclosure_class.value,
                break_glass=definition.break_glass.value,
                audit_mode="required" if definition.audit_required else "optional",
            )
        )
    roles = tuple(
        RoleDescriptionDTO(
            contract.role.value,
            contract.label,
            contract.purpose,
            frozenset(scope.value for scope in contract.permitted_scope_types),
        )
        for contract in sorted(
            ROLE_CONTRACTS.values(), key=lambda item: item.role.value
        )
    )
    return AuthorizationCatalogueDTO(tuple(actions), roles)
