"""Central Flask guard that rejects every unclassified endpoint."""

from __future__ import annotations

from collections.abc import Callable

from flask import current_app, jsonify, request

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


def install_default_deny(app, *, authenticated: Callable[[], bool]) -> None:
    """Install endpoint classification enforcement before handler execution."""

    @app.before_request
    def _authorization_default_deny():
        if request.endpoint == "static":
            return None
        policy = endpoint_policy(request.endpoint)
        if policy is None:
            _record_unclassified_endpoint()
            return jsonify({"error": "not_authorized"}), 403
        if policy.mode in {EndpointMode.PUBLIC, EndpointMode.SIGNED_RESOURCE}:
            return None
        if policy.mode is EndpointMode.MOBILE_SESSION:
            view = current_app.view_functions.get(request.endpoint)
            if view is not None and getattr(view, "_token_auth_applied", False):
                return None
            return jsonify({"error": "not_authorized"}), 403
        if policy.mode is EndpointMode.AUTOMATION:
            return jsonify({"error": "not_authorized"}), 403
        if not authenticated():
            return jsonify({"error": "not_authorized"}), 403
        return None
