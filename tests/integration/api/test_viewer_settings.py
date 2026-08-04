import pytest


def test_viewer_preset_round_trips_color_tuning(app, test_users):
    payload = {
        "name": "Calibrated red-free",
        "brightness": 1.12,
        "contrast": 1.18,
        "saturation": 0.9,
        "red_luminance": 0.8,
        "red_saturation": 0.75,
        "green_luminance": 1.3,
        "green_saturation": 1.2,
        "blue_luminance": 0.7,
        "blue_saturation": 0.65,
        "gamma": 0.82,
        "black_point": -0.03,
        "white_point": 0.94,
        "shadow_lift": 0.45,
        "flattening": 0.2,
        "invert": True,
        "filter": "redfreeenhanced",
    }

    with app.test_client(user=test_users["resident"]) as client:
        saved = client.post("/api/viewer/presets/4", json=payload)
        fetched = client.get("/api/viewer/presets")

    assert saved.status_code == 200
    assert fetched.status_code == 200
    preset = fetched.get_json()["4"]
    for key, expected in payload.items():
        if isinstance(expected, float):
            assert preset[key] == pytest.approx(expected)
        else:
            assert preset[key] == expected


def test_viewer_preset_color_tuning_defaults_to_neutral_and_is_clamped(app, test_users):
    with app.test_client(user=test_users["resident"]) as client:
        saved = client.post(
            "/api/viewer/presets/3",
            json={
                "name": "Clamp test",
                "saturation": -5,
                "red_luminance": 9,
                "gamma": 99,
                "black_point": -4,
                "flattening": 5,
                "filter": "none",
            },
        )
        fetched = client.get("/api/viewer/presets")

    assert saved.status_code == 200
    preset = fetched.get_json()["3"]
    assert preset["saturation"] == 0
    assert preset["red_luminance"] == 3
    assert preset["red_saturation"] == 1
    assert preset["green_luminance"] == 1
    assert preset["green_saturation"] == 1
    assert preset["blue_luminance"] == 1
    assert preset["blue_saturation"] == 1
    assert preset["gamma"] == 2.5
    assert preset["black_point"] == -0.2
    assert preset["white_point"] == 1
    assert preset["flattening"] == 1
    assert preset["invert"] is False


def test_viewer_preset_does_not_expose_removed_detail_controls(app, test_users):
    with app.test_client(user=test_users["resident"]) as client:
        saved = client.post(
            "/api/viewer/presets/5",
            json={
                "highlight_protection": 0.7,
                "local_contrast": 0.6,
                "denoise": 0.5,
                "sharpen": 0.4,
            },
        )
        preset = client.get("/api/viewer/presets").get_json()["5"]

    assert saved.status_code == 200
    for key in ("highlight_protection", "local_contrast", "denoise", "sharpen"):
        assert key not in preset


def test_viewer_preset_ignores_viewport_and_loupe_state(app, test_users):
    with app.test_client(user=test_users["resident"]) as client:
        saved = client.post(
            "/api/viewer/presets/2",
            json={
                "name": "Color only",
                "brightness": 1.1,
                "zoom": 240,
                "pan_x": 90,
                "pan_y": -45,
                "loupe_size": 320,
                "loupe_zoom": 3.5,
                "loupe_enabled": True,
            },
        )
        preset = client.get("/api/viewer/presets").get_json()["2"]

    assert saved.status_code == 200
    assert preset["brightness"] == pytest.approx(1.1)
    for key in ("zoom", "pan_x", "pan_y", "loupe_size", "loupe_zoom", "loupe_enabled"):
        assert key not in preset


def test_viewer_preset_accepts_protected_shadow_lift_mode(app, test_users):
    with app.test_client(user=test_users["resident"]) as client:
        saved = client.post(
            "/api/viewer/presets/1",
            json={"name": "Protected shadow lift", "filter": "enhance", "shadow_lift": 0.5},
        )
        preset = client.get("/api/viewer/presets").get_json()["1"]

    assert saved.status_code == 200
    assert preset["filter"] == "enhance"
    assert preset["shadow_lift"] == pytest.approx(0.5)
