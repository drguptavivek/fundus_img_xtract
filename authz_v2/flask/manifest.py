"""Deterministic projection of live Flask routes and authorization metadata."""

from __future__ import annotations

from dataclasses import dataclass

from authz_v2.core.catalogue import CATALOGUE
from authz_v2.flask.contracts import EndpointPolicy


@dataclass(frozen=True)
class RouteAuthorizationDTO:
    endpoint: str
    methods: tuple[str, ...]
    path: str
    mode: str | None
    action: str | None
    enforcement: str | None
    resolver: str | None
    resource_type: str | None
    disclosure_class: str | None
    audit_required: bool | None


def build_route_manifest(app) -> tuple[RouteAuthorizationDTO, ...]:
    """Describe every non-static route, including explicit unclassified rows."""
    rows: list[RouteAuthorizationDTO] = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        view = app.view_functions.get(rule.endpoint)
        policy: EndpointPolicy | None = getattr(view, "__authz_endpoint_policy__", None)
        definition = CATALOGUE[policy.action] if policy else None
        rows.append(
            RouteAuthorizationDTO(
                endpoint=rule.endpoint,
                methods=tuple(sorted(set(rule.methods or ()) - {"HEAD", "OPTIONS"})),
                path=str(rule),
                mode=policy.mode.value if policy else None,
                action=policy.action.value if policy else None,
                enforcement=policy.enforcement if policy else None,
                resolver=policy.resolver if policy else None,
                resource_type=definition.resource_type if definition else None,
                disclosure_class=(
                    definition.disclosure_class.value if definition else None
                ),
                audit_required=definition.audit_required if definition else None,
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.endpoint, row.path, row.methods)))
