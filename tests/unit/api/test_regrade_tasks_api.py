from __future__ import annotations

from types import SimpleNamespace

import jwt

from models import User
from regrade.errors import denied


def test_create_regrade_tasks_json_api_builds_typed_command(
    client, login_user, monkeypatch
):
    login_user("test_admin", "Test@2026")
    captured = {}

    def fake_create(db, *, actor, command):
        captured["actor_id"] = actor.id
        captured["command"] = command
        return {
            "created_count": 2,
            "skipped_pending_count": 1,
            "regrade_task_ids": [31, 32],
        }

    monkeypatch.setattr("api.regrade_tasks.create_regrade_tasks", fake_create)
    response = client.post(
        "/api/regrade-tasks",
        json={
            "disease_id": 1,
            "assigned_to_user_id": 2,
            "notes": "Resolve discordance",
            "project_id": 3,
            "filters": {"resident_grade": ["Normal"]},
        },
    )

    assert response.status_code == 201
    assert response.get_json()["result"] == {
        "created_count": 2,
        "skipped_pending_count": 1,
        "regrade_task_ids": [31, 32],
    }
    assert captured["command"].project_id == 3
    assert captured["command"].filters["resident_grade"] == ["Normal"]


def test_create_regrade_tasks_htmx_form_uses_same_api(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def fake_create(db, *, actor, command):
        captured["command"] = command
        return {
            "created_count": 1,
            "skipped_pending_count": 0,
            "regrade_task_ids": [44],
        }

    monkeypatch.setattr("api.regrade_tasks.create_regrade_tasks", fake_create)
    response = client.post(
        "/api/regrade-tasks",
        data={
            "disease_id": "1",
            "assigned_to_user_id": "2",
            "regrade_notes": "HTMX queue",
            "resident_grade": ["Normal", "Refer"],
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 204
    assert response.headers["HX-Redirect"]
    assert captured["command"].notes == "HTMX queue"
    assert captured["command"].filters["resident_grade"] == ["Normal", "Refer"]


def test_create_regrade_tasks_mobile_bearer_bypasses_browser_csrf(
    app, client, db_session, monkeypatch
):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    actor = db_session.query(User).filter_by(username="test_admin").one()
    monkeypatch.setenv("JWT_SECRET", "regrade-mobile-test-secret")
    monkeypatch.setattr(
        "auth.decorators.validate_access_session",
        lambda db, claims: SimpleNamespace(
            session=SimpleNamespace(id=71, device_id="test-device"),
            user=actor,
        ),
    )
    monkeypatch.setattr(
        "api.regrade_tasks.create_regrade_tasks",
        lambda db, *, actor, command: {
            "created_count": 1,
            "skipped_pending_count": 0,
            "regrade_task_ids": [91],
        },
    )
    token = jwt.encode(
        {"sub": str(actor.id), "typ": "access"},
        "regrade-mobile-test-secret",
        algorithm="HS256",
    )
    response = client.post(
        "/api/regrade-tasks",
        json={
            "disease_id": 1,
            "assigned_to_user_id": actor.id,
            "notes": "Mobile cohort",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.get_json()["result"]["regrade_task_ids"] == [91]


def test_invalid_mobile_bearer_reaches_authentication_not_csrf(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    monkeypatch.setenv("JWT_SECRET", "regrade-mobile-test-secret")

    response = client.post(
        "/api/regrade-tasks",
        json={"disease_id": 1},
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401


def test_authenticated_browser_cannot_bypass_csrf_with_bearer_header(
    app, client, login_user, monkeypatch
):
    login_user("test_admin", "Test@2026")
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)

    response = client.post(
        "/api/regrade-tasks",
        json={"disease_id": 1},
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 400


def test_submit_regrade_api_supports_json_and_fails_closed(
    client, login_user, monkeypatch
):
    login_user("test_admin", "Test@2026")

    def fake_submit(db, *, actor, regrade_task_id, command):
        assert regrade_task_id == 17
        assert command.selected_feature_ids == (4, 5)
        return {
            "regrade_task_id": 17,
            "source_task_id": 21,
            "grade_id": 8,
            "status": "regrade_done",
            "consensus_method": "regrade",
        }

    monkeypatch.setattr("api.regrade_tasks.submit_regrade", fake_submit)
    response = client.post(
        "/api/regrade-tasks/17/submission",
        json={
            "label_id": 9,
            "selected_feature_ids": [4, 5],
            "feature_geometry_json": "",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["submission"]["status"] == "regrade_done"

    monkeypatch.setattr(
        "api.regrade_tasks.submit_regrade",
        lambda *args, **kwargs: (_ for _ in ()).throw(denied("Not assigned.")),
    )
    denied_response = client.post(
        "/api/regrade-tasks/17/submission",
        json={
            "label_id": 9,
            "selected_feature_ids": [],
            "feature_geometry_json": None,
        },
    )
    assert denied_response.status_code == 403
    assert denied_response.get_json()["error"]["code"] == "authorization_denied"


def test_submit_regrade_htmx_form_uses_same_api(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def fake_submit(db, *, actor, regrade_task_id, command):
        captured["command"] = command
        return {
            "regrade_task_id": regrade_task_id,
            "source_task_id": 21,
            "grade_id": 8,
            "status": "regrade_done",
            "consensus_method": "regrade",
        }

    monkeypatch.setattr("api.regrade_tasks.submit_regrade", fake_submit)
    response = client.post(
        "/api/regrade-tasks/17/submission",
        data={
            "label_id": "9",
            "selected_features": ["4", "5"],
            "feature_geometry_json": "",
            "action": "save_next",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 204
    assert response.headers["HX-Redirect"].endswith("/regrade-tasks/random")
    assert captured["command"].selected_feature_ids == (4, 5)


def test_regrade_api_rejects_incomplete_submission_facts(client, login_user):
    login_user("test_admin", "Test@2026")

    response = client.post(
        "/api/regrade-tasks/17/submission",
        json={"label_id": 9},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_regrade_api_rejects_invalid_scalar_cohort_filter(client, login_user):
    login_user("test_admin", "Test@2026")

    response = client.post(
        "/api/regrade-tasks",
        json={
            "disease_id": 1,
            "assigned_to_user_id": 2,
            "notes": "Invalid cohort must deny",
            "filters": {"has_arbitrator": "garbage"},
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"
