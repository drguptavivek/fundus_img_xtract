"""Structural gates for the fail-closed application authentication boundary."""

from app import PUBLIC_SESSION_PATHS, PUBLIC_SESSION_PREFIXES, is_public_mobile_pwa_path


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


def test_mobile_pwa_exposes_only_its_app_shell_without_login():
    for public in (
        "/mobile/",
        "/mobile/index.html",
        "/mobile/main.dart.js",
        "/mobile/manifest.json",
        "/mobile/assets/FontManifest.json",
        "/mobile/canvaskit/canvaskit.wasm",
        "/mobile/icons/Icon-192.png",
    ):
        assert is_public_mobile_pwa_path(public), public
    for private in (
        "/mobile/download/android",
        "/mobile/download/android-bundle",
        "/mobile/.last_build_id",
        "/mobile/assets/../.last_build_id",
        "/mobile/canvaskit/canvaskit.js.symbols",
        "/mobile/flutter.js.map",
        "/mobile/anything-else",
        "/mobile/assets",
    ):
        assert not is_public_mobile_pwa_path(private), private


def test_anonymous_mobile_requests_outside_app_shell_go_to_login(client, tmp_path):
    pwa_root = tmp_path / "mobile-pwa"
    pwa_root.mkdir()
    (pwa_root / "index.html").write_text("<html>pwa</html>", encoding="utf-8")
    (pwa_root / ".last_build_id").write_text("abc", encoding="utf-8")
    client.application.config["MOBILE_PWA_ROOT"] = str(pwa_root)

    assert client.get("/mobile/").status_code == 200
    for private in ("/mobile/.last_build_id", "/mobile/download/android", "/mobile/some/page"):
        response = client.get(private)
        assert response.status_code in (302, 401), private
        if response.status_code == 302:
            assert "/login" in response.headers["Location"], private
