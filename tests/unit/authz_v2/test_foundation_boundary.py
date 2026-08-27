from __future__ import annotations

from pathlib import Path


def test_authz_v2_is_not_registered_in_live_application():
    app = Path("app.py").read_text(encoding="utf-8")
    api_init = Path("api/__init__.py").read_text(encoding="utf-8")
    assert "authz_v2" not in app
    assert "install_default_deny" not in app
    assert "authorization" not in api_init


def test_staged_authorization_api_declares_its_inactive_boundary():
    source = Path("api/authorization.py").read_text(encoding="utf-8")
    assert "intentionally not imported" in source
    assert '@api_bp.get("/authorization/catalogue")' in source
    assert '@api_bp.post("/authorization/grants")' in source
    assert '@api_bp.get("/authorization/me/capabilities")' in source
    assert '@api_bp.get("/authorization/me/workspaces")' in source
    assert '@api_bp.get("/authorization/me/upload-options")' in source
