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
