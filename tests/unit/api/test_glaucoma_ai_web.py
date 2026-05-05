from __future__ import annotations

from itertools import count

from tests.helpers.factories import UserFactory


_SEQUENCE = count(1)


def test_glaucoma_ai_recent_results_partial_is_paginated(client, login_user, db_session, monkeypatch):
    import glaucoma_ai.routes as routes

    suffix = next(_SEQUENCE)
    user = UserFactory.create_by_role(db_session, "fileUploader", username=f"glaucoma_ai_web_{suffix}")
    captured = {}

    def fake_load_recent(db, *, limit: int, offset: int):
        captured["limit"] = limit
        captured["offset"] = offset
        return [
            _recent_item("image-a", "a.jpg"),
            _recent_item("image-b", "b.jpg"),
            _recent_item("image-c", "c.jpg"),
        ]

    monkeypatch.setattr(routes, "_load_web_recent_uploads", fake_load_recent)
    login_user(user.username, "Test@2026")

    response = client.get("/glaucoma-ai/recent?limit=2&offset=2")

    assert response.status_code == 200
    assert captured == {"limit": 3, "offset": 2}
    html = response.get_data(as_text=True)
    assert "Page 2" in html
    assert "your uploads only" in html
    assert "a.jpg" in html
    assert "b.jpg" in html
    assert "c.jpg" not in html
    assert "offset=0" in html
    assert "offset=4" in html


def test_glaucoma_ai_recent_results_json_uses_requested_page(client, login_user, db_session, monkeypatch):
    import glaucoma_ai.routes as routes

    suffix = next(_SEQUENCE)
    user = UserFactory.create_by_role(db_session, "fileUploader", username=f"glaucoma_ai_json_{suffix}")
    captured = {}

    def fake_updates(db, user_id: int, *, limit: int, offset: int):
        captured["user_id"] = user_id
        captured["limit"] = limit
        captured["offset"] = offset
        return [{"image_uuid": "image-a", "filename": "a.jpg"}]

    monkeypatch.setattr(routes, "load_user_glaucoma_ai_inference_updates", fake_updates)
    login_user(user.username, "Test@2026")

    response = client.get("/glaucoma-ai/recent/results?limit=7&offset=14")

    assert response.status_code == 200
    assert captured == {"user_id": user.id, "limit": 7, "offset": 14}
    payload = response.get_json()
    assert payload["limit"] == 7
    assert payload["offset"] == 14
    assert payload["count"] == 1


def _recent_item(image_uuid: str, filename: str) -> dict:
    return {
        "image_uuid": image_uuid,
        "filename": filename,
        "image_url": f"/media/{image_uuid}.jpg",
        "thumbnail_url": f"/media/{image_uuid}-thumb.jpg",
        "task_uuid": f"task-{image_uuid}",
        "inference": {"status": "success", "grade_impression": "Glaucoma", "confidence": 0.8},
    }
