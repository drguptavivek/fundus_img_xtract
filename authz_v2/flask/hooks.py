"""Central Flask guard that rejects every unclassified endpoint."""

from __future__ import annotations

from collections.abc import Callable

from flask import current_app, g, jsonify, request

from authz_v2.flask.contracts import EndpointMode, EndpointPolicy
from authz_v2.telemetry.metrics import increment


def _record_unclassified_endpoint() -> None:
    try:
        increment("authz_unclassified_endpoint_total")
    except Exception:  # noqa: BLE001 - telemetry cannot relax default deny
        return


def endpoint_policy(endpoint: str | None) -> EndpointPolicy | None:
    if not endpoint:
        return None
    view = current_app.view_functions.get(endpoint)
    return getattr(view, "__authz_endpoint_policy__", None) if view else None


def unclassified_endpoints(app) -> tuple[str, ...]:
    """Return live application endpoints missing explicit authz metadata."""
    return tuple(
        sorted(
            rule.endpoint
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
            and getattr(
                app.view_functions.get(rule.endpoint), "__authz_endpoint_policy__", None
            )
            is None
        )
    )


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
        resolver = resource_resolvers.get(policy.resolver) if policy.resolver else None
        definition_requires_resource = policy.resolver is not None
        if definition_requires_resource and resolver is None:
            return jsonify({"error": "not_authorized"}), 403
        try:
            db = database()
            resource = resolver(dict(request.view_args or {})) if resolver else None
            if definition_requires_resource and resource is None:
                return jsonify({"error": "not_authorized"}), 403
            service = decision_service(db)
            receipt = service.require(
                db,
                principal(),
                policy.action,
                resource,
                audit_service=audit_service(db) if audit_service else None,
            )
        except Exception:  # noqa: BLE001 - all incomplete/invalid auth context denies
            return jsonify({"error": "not_authorized"}), 403
        g.authorization_receipt = receipt
        return None
