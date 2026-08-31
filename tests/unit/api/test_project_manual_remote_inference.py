from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from api import remote_inference as routes
from remote_inference.dr_dme import CandidatePage
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


def test_create_dr_dme_encounter_job_api_uses_encounter_contract(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def create_manual_job(**kwargs):
        captured.update(kwargs)
        return MutationResult(True, "Queued.", payload={"job_token": "job-1"}, status_code=202)

    monkeypatch.setattr(routes.encounter_service, "create_manual_job", create_manual_job)
    response = client.post(
        "/api/remote-inference/encounter-set-jobs",
        json={"project_id": 2, "workflow": "dr_dme", "encounter_ids": [11, 12]},
    )

    assert response.status_code == 202
    assert response.get_json()["job_token"] == "job-1"
    assert captured["project_id"] == 2
    assert captured["encounter_ids"] == [11, 12]


def test_dr_dme_candidate_api_exposes_filters_images_and_pagination(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    @contextmanager
    def fake_session():
        yield SimpleNamespace(get=lambda _model, _project_id: object())

    def candidates(_db, *, filters, user):
        captured["filters"] = filters
        return CandidatePage(
            rows=({
                "encounter_id": 11,
                "encounter_uuid": "enc-11",
                "capture_date": "2026-08-18",
                "images": [{"id": 91, "uuid": "image-91", "eye": "right"}],
            },),
            encounter_count=73,
            image_count=146,
            page=2,
            page_size=50,
            has_prev=True,
            has_next=False,
        )

    monkeypatch.setattr(routes, "get_db_session", fake_session)
    monkeypatch.setattr("authz.project_access.can_run_wai", lambda *args, **kwargs: True)
    monkeypatch.setattr(routes, "list_dr_dme_candidates", candidates)

    response = client.get(
        "/api/remote-inference/encounter-set-candidates"
        "?project_id=2&workflow=dr_dme&capture_date_from=2026-08-01"
        "&capture_date_to=2026-08-19&camera_id=7&dr_report=present"
        "&eligibility=not_verified&include_prior=1&page=2&page_size=50"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["candidates"][0]["images"][0]["eye"] == "right"
    assert payload["pagination"] == {
        "page": 2, "page_size": 50, "encounter_count": 73,
        "image_count": 146, "has_prev": True, "has_next": False,
    }
    assert captured["filters"].dr_report == "present"
    assert captured["filters"].eligibility == "not_verified"
    assert captured["filters"].include_prior is True
    assert payload["filters"]["eligibility"] == "not_verified"


def test_save_dr_dme_project_workflow_api_keeps_controls_independent(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def save(user_id, project_id, payload):
        captured.update(user_id=user_id, project_id=project_id, payload=payload)
        return MutationResult(True, "Updated.")

    monkeypatch.setattr(routes.encounter_service, "save_workflow", save)
    response = client.patch(
        "/api/remote-inference/projects/2/encounter-workflows/dr-dme",
        json={"manual_enabled": True, "automatic_enabled": False, "automatic_eligibility": "always"},
    )

    assert response.status_code == 200
    assert captured["payload"]["manual_enabled"] is True
    assert captured["payload"]["automatic_enabled"] is False


def test_save_dr_dme_project_workflow_form_preserves_both_section_controls(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def save(user_id, project_id, payload):
        captured.update(user_id=user_id, project_id=project_id, payload=payload)
        return MutationResult(True, "Updated.")

    monkeypatch.setattr(routes.encounter_service, "save_workflow", save)
    response = client.post(
        "/api/remote-inference/projects/2/encounter-workflows/dr-dme",
        data={
            "manual_enabled": "on",
            "automatic_enabled": "on",
            "automatic_eligibility": "if_dr_ocr_report_present",
        },
    )

    assert response.status_code == 200
    assert captured["payload"]["manual_enabled"] is True
    assert captured["payload"]["automatic_enabled"] is True
    assert captured["payload"]["automatic_eligibility"] == "if_dr_ocr_report_present"


def test_project_template_places_dr_dme_controls_in_manual_and_automated_sections():
    template = (
        Path(__file__).resolve().parents[3]
        / "templates/admin/partials/project_detail_panel.html"
    ).read_text(encoding="utf-8")
    manual = template.split("Manual Remote AI Workflows", 1)[1].split("Automated Remote AI Inference", 1)[0]
    automated = template.split("Automated Remote AI Inference", 1)[1]

    assert "dr_dme_manual_enabled" in manual
    assert "dr_dme_automatic_enabled" not in manual
    assert 'form="drDmeAutomaticForm" name="automatic_enabled"' in automated
    assert "dr_dme_manual_enabled" not in automated
