"""Deterministic projection of live Flask routes and authorization metadata."""

from __future__ import annotations

from dataclasses import dataclass

from authz_v2.core.catalogue import CATALOGUE
from authz_v2.flask.contracts import EndpointPolicy
from authz_v2.flask.hooks import endpoint_policy_for_app


@dataclass(frozen=True)
class RouteAuthorizationDTO:
    endpoint: str
    methods: tuple[str, ...]
    path: str
    mode: str | None
    action: str | None
    actions: tuple[str, ...]
    enforcement: str | None
    resolver: str | None
    binding: str | None
    resource_type: str | None
    resource_types: tuple[str, ...]
    disclosure_class: str | None
    audit_required: bool | None


def build_route_manifest(app) -> tuple[RouteAuthorizationDTO, ...]:
    """Describe every non-static route, including explicit unclassified rows."""
    rows: list[RouteAuthorizationDTO] = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = tuple(sorted(set(rule.methods or ()) - {"HEAD", "OPTIONS"}))
        policies = tuple(
            endpoint_policy_for_app(app, rule.endpoint, method) for method in methods
        )
        policy: EndpointPolicy | None = policies[0] if policies and all(policies) else None
        declared_actions = []
        for item in policies:
            if item:
                declared_actions.extend((item.action, *item.action_variants))
        actions = tuple(dict.fromkeys(declared_actions))
        definition = CATALOGUE[actions[0]] if actions else None
        uniform = policy if policy and all(item == policy for item in policies) else None
        rows.append(
            RouteAuthorizationDTO(
                endpoint=rule.endpoint,
                methods=methods,
                path=str(rule),
                mode=(uniform.mode.value if uniform else "method_specific" if policy else None),
                action=actions[0].value if policy and actions else None,
                actions=tuple(action.value for action in actions),
                enforcement=uniform.enforcement if uniform else "method_specific" if policy else None,
                resolver=uniform.resolver if uniform else None,
                binding=uniform.binding if uniform else None,
                resource_type=definition.resource_type if definition else None,
                resource_types=tuple(
                    CATALOGUE[action].resource_type for action in actions
                ),
                disclosure_class=(
                    definition.disclosure_class.value if definition else None
                ),
                audit_required=definition.audit_required if definition else None,
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.endpoint, row.path, row.methods)))
