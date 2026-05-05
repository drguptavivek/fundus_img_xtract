from __future__ import annotations


def test_mobile_pwa_serves_index_without_browser_login(client, tmp_path):
    pwa_root = tmp_path / "mobile-pwa"
    pwa_root.mkdir()
    (pwa_root / "index.html").write_text("<html><body>Flutter PWA</body></html>", encoding="utf-8")

    client.application.config["MOBILE_PWA_ROOT"] = str(pwa_root)

    response = client.get("/mobile/")

    assert response.status_code == 200
    assert "Flutter PWA" in response.get_data(as_text=True)
    assert "no-cache" in response.headers["Cache-Control"]
    csp = response.headers["Content-Security-Policy"]
    assert "'wasm-unsafe-eval'" in csp
    assert "https://www.gstatic.com" in csp
    assert "https://fonts.gstatic.com" in csp


def test_mobile_pwa_serves_assets_and_deep_links(client, tmp_path):
    pwa_root = tmp_path / "mobile-pwa"
    pwa_root.mkdir()
    (pwa_root / "index.html").write_text("<html><body>Flutter PWA</body></html>", encoding="utf-8")
    (pwa_root / "manifest.json").write_text('{"name":"EIM"}', encoding="utf-8")

    client.application.config["MOBILE_PWA_ROOT"] = str(pwa_root)

    asset_response = client.get("/mobile/manifest.json")
    deep_link_response = client.get("/mobile/results")

    assert asset_response.status_code == 200
    assert asset_response.get_json() == {"name": "EIM"}
    assert deep_link_response.status_code == 200
    assert "Flutter PWA" in deep_link_response.get_data(as_text=True)


def test_mobile_pwa_missing_asset_returns_404_not_index(client, tmp_path):
    pwa_root = tmp_path / "mobile-pwa"
    pwa_root.mkdir()
    (pwa_root / "index.html").write_text("<html><body>Flutter PWA</body></html>", encoding="utf-8")

    client.application.config["MOBILE_PWA_ROOT"] = str(pwa_root)

    response = client.get("/mobile/flutter.js.map")

    assert response.status_code == 404
    assert response.get_data(as_text=True) == ""
