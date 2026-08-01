from contextlib import contextmanager
from types import SimpleNamespace

from api import remote_inference as routes
from upload_profiles.admin_service import MutationResult


def test_save_project_manual_workflow_api_parses_project_configuration(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def save(user_id, project_id, workflows):
        captured.update(user_id=user_id, project_id=project_id, workflows=workflows)
        return MutationResult(True, "Manual remote inference workflows updated.", payload={"project_id": project_id})

    monkeypatch.setattr(routes.manual_service, "set_project_manual_workflows", save)

    response = client.post(
        "/api/remote-inference/projects/17/manual-workflows",
        data={"manual_remote_inference_workflow": "1:2:encounter_set"},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert captured["project_id"] == 17
    assert captured["workflows"] == [
        routes.manual_service.ManualRemoteInferenceWorkflowKey(
            disease_id=1,
            ai_model_id=2,
            upload_kind="encounter_set",
        )
    ]


def test_get_project_manual_workflow_api_returns_options(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    monkeypatch.setattr(routes, "manager_lab_unit_ids", lambda _user_id: {1})

    @contextmanager
    def fake_session():
        yield SimpleNamespace(get=lambda _model, _project_id: object())

    monkeypatch.setattr(routes, "get_db_session", fake_session)
    monkeypatch.setattr(
        routes.manual_service,
        "project_manual_workflow_context",
        lambda _db, _project_id: {
            "manual_remote_inference_workflows": [
                SimpleNamespace(
                    disease_id=1,
                    disease_name="Glaucoma",
                    ai_model_id=2,
                    ai_model_name="Wadhwani",
                    ai_model_version="1",
                    provider="wadhwani_glaucoma",
                    upload_kind="encounter_set",
                    enabled=True,
                )
            ]
        },
    )

    response = client.get("/api/remote-inference/projects/17/manual-workflows")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["manual_workflows"][0]["enabled"] is True
    assert payload["manual_workflows"][0]["upload_kind"] == "encounter_set"


def test_resume_interrupted_wadhwani_job_api(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def resume(*, job_token, user_id):
        captured.update(job_token=job_token, user_id=user_id)
        return MutationResult(True, "Resumed 2 unfinished Wadhwani inference task(s).", payload={"resumed_task_count": 2})

    monkeypatch.setattr(routes.job_service, "resume_interrupted_wadhwani_job", resume)

    response = client.post(
        "/api/remote-inference/wadhwani/encounter-set-jobs/batch-token/resume",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json()["resumed_task_count"] == 2
    assert captured["job_token"] == "batch-token"
