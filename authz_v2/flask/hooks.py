"""Central Flask guard that rejects every unclassified endpoint."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from flask import current_app, g, jsonify, request

from authz_v2.flask.contracts import EndpointMode, EndpointPolicy
from authz_v2.flask.route_catalogue import catalogued_endpoint_policy
from authz_v2.telemetry.metrics import increment


@dataclass(frozen=True)
class RequestAuthorizationInput(Mapping[str, object]):
    """Transport facts available to a named resolver without merging namespaces."""

    path: Mapping[str, object]
    query: Mapping[str, str]
    form: Mapping[str, str]
    json: Mapping[str, Any]

    def __getitem__(self, key: str) -> object:
        return self.path[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.path)

    def __len__(self) -> int:
        return len(self.path)


def _request_authorization_input() -> RequestAuthorizationInput:
    payload = request.get_json(silent=True)
    return RequestAuthorizationInput(
        path=dict(request.view_args or {}),
        query=request.args.to_dict(flat=True),
        form=request.form.to_dict(flat=True),
        json=dict(payload) if isinstance(payload, dict) else {},
    )


def _record_unclassified_endpoint() -> None:
    try:
        increment("authz_unclassified_endpoint_total")
    except Exception:  # noqa: BLE001 - telemetry cannot relax default deny
        return


def endpoint_policy(endpoint: str | None) -> EndpointPolicy | None:
    if not endpoint:
        return None
    view = current_app.view_functions.get(endpoint)
    decorated = getattr(view, "__authz_endpoint_policy__", None) if view else None
    return decorated or catalogued_endpoint_policy(endpoint)


def unclassified_endpoints(app) -> tuple[str, ...]:
    """Return live application endpoints missing explicit authz metadata."""
    return tuple(
        sorted(
            rule.endpoint
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
            and endpoint_policy_for_app(app, rule.endpoint) is None
        )
    )


def endpoint_policy_for_app(app, endpoint: str) -> EndpointPolicy | None:
    view = app.view_functions.get(endpoint)
    decorated = getattr(view, "__authz_endpoint_policy__", None) if view else None
    return decorated or catalogued_endpoint_policy(endpoint)


def install_default_deny(
    app,
    *,
    authenticated: Callable[[], bool],
    principal: Callable[[], object] | None = None,
    database: Callable[[], object] | None = None,
    decision_service: Callable[[object], object] | None = None,
    resource_resolvers: dict[str, Callable[[object], object]] | None = None,
    audit_service: Callable[[object], object] | None = None,
) -> None:
    """Install endpoint classification enforcement before handler execution."""

    @app.before_request
    def _authorization_default_deny():
        if request.endpoint == "static":
            return None
        policy = endpoint_policy(request.endpoint)
        if policy is None:
            _record_unclassified_endpoint()
            return jsonify({"error": "not_authorized"}), 403
        if policy.mode is EndpointMode.PUBLIC and policy.resolver is None:
            return None
        if policy.mode is EndpointMode.SCREEN:
            if authenticated():
                return None
            return jsonify({"error": "not_authorized"}), 403
        dependencies = (
            principal,
            database,
            decision_service,
            resource_resolvers,
        )
        if any(item is None for item in dependencies):
            return jsonify({"error": "not_authorized"}), 403
        resolver_name = policy.binding or policy.resolver
        resolver = resource_resolvers.get(resolver_name) if resolver_name else None
        definition_requires_resource = resolver_name is not None
        if definition_requires_resource and resolver is None:
            return jsonify({"error": "not_authorized"}), 403
        try:
            db = database()
            resolved = (
                resolver(db, _request_authorization_input()) if resolver else None
            )
            if policy.binding:
                selected_action, resource = resolved
                allowed_actions = {policy.action, *policy.action_variants}
                if selected_action not in allowed_actions:
                    raise PermissionError("resolver selected an undeclared action")
            else:
                selected_action, resource = policy.action, resolved
            if definition_requires_resource and resource is None:
                return jsonify({"error": "not_authorized"}), 403
            service = decision_service(db)
            receipt = service.require(
                db,
                principal(),
                selected_action,
                resource,
                audit_service=audit_service(db) if audit_service else None,
            )
        except Exception:  # noqa: BLE001 - all incomplete/invalid auth context denies
            return jsonify({"error": "not_authorized"}), 403
        g.authorization_receipt = receipt
        return None
