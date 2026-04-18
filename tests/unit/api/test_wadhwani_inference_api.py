from services.wadhwani_glaucoma_inference import WadhwaniInferenceResult


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
