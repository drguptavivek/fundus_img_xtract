from contextlib import contextmanager
from types import SimpleNamespace

from authz import RecordScope
from services.wadhwani_glaucoma_inference import WadhwaniInferenceResult
from upload_profiles.admin_service import MutationResult


def test_wadhwani_inference_api_returns_service_payload(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")

    monkeypatch.setattr(
        "api.ai_models.run_task_inference",
        lambda **kwargs: WadhwaniInferenceResult(
            task_id=123,
            ai_model_id=7,
            inference_run_id=55,
            grade_id=901,
            status="success",
            message="Inference completed successfully.",
            reused_existing_grade=False,
            prediction_id="pred-123",
            confidence=0.98,
            predicted_class=1,
            predicted_class_name="Glaucoma Present",
            grade_impression="Glaucoma",
        ),
    )
    monkeypatch.setattr(
        "api.ai_models.task_record_scope",
        lambda _context, _task: RecordScope.classical(lab_unit_id=1, hospital_id=1),
    )
    monkeypatch.setattr(
        "api.ai_models.access_context",
        lambda _db, _user: SimpleNamespace(
            has_any_global_role=lambda _roles: False,
        ),
    )
    monkeypatch.setattr(
        "api.ai_models.admin_scope",
        lambda _context: SimpleNamespace(allowed=True),
    )
    monkeypatch.setattr(
        "api.ai_models.assigned_lab_scope",
        lambda *_args: SimpleNamespace(allowed=False),
    )
    monkeypatch.setattr(
        "api.ai_models.hospital_scope",
        lambda *_args: SimpleNamespace(allowed=False),
    )

    @contextmanager
    def fake_transaction():
        yield SimpleNamespace(get=lambda _model, _task_id: SimpleNamespace(id=_task_id))

    monkeypatch.setattr("api.ai_models.transaction_scope", fake_transaction)

    response = client.post("/api/ai-models/wadhwani-glaucoma/tasks/123/infer", json={"force": False})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task_id"] == 123
    assert payload["ai_model_id"] == 7
    assert payload["grade_impression"] == "Glaucoma"


def test_madhunetra_integration_api_never_echoes_token(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def save(payload):
        captured.update(payload)
        return MutationResult(True, "Updated.")

    monkeypatch.setattr("api.ai_models.encounter_service.save_integration", save)
    response = client.patch(
        "/api/ai-models/madhunetra-dr-dme/integration",
        json={
            "api_base_url": "https://wai.example",
            "environment": "staging",
            "access_token": "plain-secret",
            "is_enabled": True,
        },
    )

    assert response.status_code == 200
    assert captured["access_token"] == "plain-secret"
    assert "plain-secret" not in response.get_data(as_text=True)


def test_madhunetra_integration_api_accepts_admin_form(client, login_user, monkeypatch):
    login_user("test_admin", "Test@2026")
    captured = {}

    def save(payload):
        captured.update(payload)
        return MutationResult(True, "Updated.")

    monkeypatch.setattr("api.ai_models.encounter_service.save_integration", save)
    response = client.post(
        "/api/ai-models/madhunetra-dr-dme/integration",
        data={
            "api_base_url": "https://wai.example",
            "environment": "production",
            "access_token": "form-secret",
            "is_enabled": "on",
        },
    )

    assert response.status_code == 200
    assert captured["is_enabled"] is True
    assert captured["access_token"] == "form-secret"
    assert "form-secret" not in response.get_data(as_text=True)
