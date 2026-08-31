"""Structural gates for the fail-closed application authentication boundary."""

from app import PUBLIC_SESSION_PATHS, PUBLIC_SESSION_PREFIXES


def test_global_login_guard_has_no_data_route_prefix_exemptions(app):
    assert "/datasets/download" not in PUBLIC_SESSION_PATHS
    assert "/api/mobile/v1/auth/" not in PUBLIC_SESSION_PREFIXES
    assert "/api/analytics/" not in PUBLIC_SESSION_PREFIXES
    assert "/mobile/" not in PUBLIC_SESSION_PREFIXES
    assert any(
        callback.__name__ == "_require_login_everywhere"
        for callback in app.before_request_funcs.get(None, ())
    )


def test_exact_credential_routes_are_explicitly_marked(app):
    credential_endpoints = {
        "mobile_api.login",
        "mobile_api.refresh",
        "mobile_api.logout",
        "datasets.download_welcome",
        "datasets.download_status",
        "datasets.download_verify",
        "datasets.download_generate",
        "datasets.download_regenerate",
        "datasets.download_accept",
        "datasets.download_file",
    }
    missing = {
        endpoint
        for endpoint in credential_endpoints
        if endpoint not in app.view_functions
        or not getattr(
            app.view_functions[endpoint], "_credential_auth_applied", False
        )
    }
    assert missing == set()
