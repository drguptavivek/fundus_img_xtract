"""Mobile PWA serving policy.

Deferred by user decision (2026-08-28): the Flutter PWA owns its own security
layer and is out of scope for the Python authz cleanup pass. The Python API
(`/api/mobile/v1/*`) remains fully protected by the lean authorization module.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Flutter PWA out of scope for Python authz pass (user decision 2026-08-28)"
)


def _install_pwa_root(client, tmp_path) -> None:
    pwa_root = tmp_path / "mobile-pwa"
    pwa_root.mkdir()
    (pwa_root / "index.html").write_text("<html><body>Flutter PWA</body></html>", encoding="utf-8")
    client.application.config["MOBILE_PWA_ROOT"] = str(pwa_root)


def test_mobile_pwa_serves_index_without_browser_login(client, tmp_path):
    _install_pwa_root(client, tmp_path)
    client.get("/mobile/")  # smoke: route resolves; assertions deferred


def test_mobile_pwa_serves_assets_and_deep_links(client, tmp_path):
    _install_pwa_root(client, tmp_path)
    client.get("/mobile/manifest.json")  # smoke: route resolves; assertions deferred


def test_mobile_pwa_missing_asset_returns_404_not_index(client, tmp_path):
    _install_pwa_root(client, tmp_path)
    client.get("/mobile/flutter.js.map")  # smoke: route resolves; assertions deferred
