from pathlib import Path
from uuid import uuid4

from models import (
    AIInferenceRun,
    AIModel,
    AIModelIntegration,
    DIRECT_UPLOAD_DIR,
    Disease,
    DirectImageUpload,
    Grade,
    GradingTask,
    LabUnit,
    User,
)
from services.wadhwani_glaucoma_inference import run_task_inference


def _linked_integration(db_session):
    for integration in db_session.query(AIModelIntegration).filter_by(provider="wadhwani_glaucoma").all():
        integration.is_enabled = False

    model = AIModel(name=f"wai_glaucoma_runtime_{uuid4().hex[:8]}", version="1.0", description="runtime")
    db_session.add(model)
    db_session.flush()
    integration = AIModelIntegration(
        ai_model_id=model.id,
        provider="wadhwani_glaucoma",
        client_id="client-123",
        bearer_token="secret-token",
    )
    db_session.add(integration)
    db_session.flush()
    return model, integration


def _ai_system(db_session):
    user = db_session.query(User).filter_by(username="ai_system").one_or_none()
    if user is None:
        user = User(
            username="ai_system",
            password_hash="not-used",
            is_active=False,
            full_name="AI System",
            designation="System",
        )
        db_session.add(user)
        db_session.flush()
    return user


def _direct_task(db_session):
    glaucoma = db_session.query(Disease).filter_by(name="Glaucoma").one()
    lab_unit = db_session.query(LabUnit).filter_by(id=100).one()
    uploader = db_session.query(User).filter_by(username="test_admin").one()
    image = DirectImageUpload(
        uuid=str(uuid4()),
        original_filename="service_image.jpg",
        filename="service_image.jpg",
        folder_rel=f"service_test_{uuid4().hex[:8]}",
        file_hash="0123456789abcdef0123456789abcdef",
        uploader_id=uploader.id,
        hospital_id=lab_unit.hospital_id,
        lab_unit_id=lab_unit.id,
        camera_id=1,
        disease_id=glaucoma.id,
        area_id=1,
    )
    db_session.add(image)
    db_session.flush()

    image_dir = DIRECT_UPLOAD_DIR / image.folder_rel
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / image.filename).write_bytes(b"fake-image-bytes")

    task = GradingTask(
        direct_image_upload_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
    )
    db_session.add(task)
    db_session.flush()
    return task


def test_run_task_inference_creates_grade_and_run_for_direct_image(app, db_session, monkeypatch):
    model, integration = _linked_integration(db_session)
    task = _direct_task(db_session)
    _ai_system(db_session)

    monkeypatch.setattr(
        "services.wadhwani_glaucoma_inference.initialize_prediction",
        lambda **kwargs: {
            "prediction_id": "pred-123",
            "results": [{"upload_url": "https://upload.example/test"}],
        },
    )
    monkeypatch.setattr("services.wadhwani_glaucoma_inference.upload_prediction_file", lambda **kwargs: None)
    monkeypatch.setattr(
        "services.wadhwani_glaucoma_inference.execute_prediction",
        lambda **kwargs: {
            "prediction_id": "pred-123",
            "external_request_id": kwargs["external_request_id"],
            "results": [
                {
                    "prediction": "referrable",
                    "model_score": 0.98,
                    "confidence": 0.98,
                    "predicted_class": 1,
                    "predicted_class_name": "Glaucoma Present",
                }
            ],
        },
    )

    result = run_task_inference(task_id=task.id, requested_by_user_id=None, force=False)

    assert result.status == "success", result.message
    grade = db_session.query(Grade).filter_by(task_id=task.id, ai_model_id=model.id).one()
    assert grade.grade_name == "Glaucoma"
    assert "AI probability: 0.9800" in (grade.comment or "")

    run = db_session.query(AIInferenceRun).filter_by(task_id=task.id, ai_model_id=model.id).one()
    assert run.status == "success"
    assert run.prediction_id == "pred-123"
    assert run.request_manifest_json["camera_type"] == "Remedio FOP"


def test_run_task_inference_reuses_cached_successful_run(app, db_session):
    model, integration = _linked_integration(db_session)
    task = _direct_task(db_session)
    ai_system = _ai_system(db_session)

    cached_run = AIInferenceRun(
        task_id=task.id,
        ai_model_id=model.id,
        integration_id=integration.id,
        source="internal",
        status="success",
        prediction_id="pred-cached",
        execute_response_json={
            "prediction_id": "pred-cached",
            "external_request_id": "cached-request",
            "results": [
                {
                    "prediction": "referrable",
                    "model_score": 0.77,
                    "confidence": 0.77,
                    "predicted_class": 1,
                    "predicted_class_name": "Glaucoma Present",
                }
            ],
        },
    )
    db_session.add(cached_run)
    db_session.flush()

    result = run_task_inference(task_id=task.id, requested_by_user_id=ai_system.id, force=True)

    assert result.status == "success", result.message
    assert result.reused_existing_grade is True
    grade = db_session.query(Grade).filter_by(task_id=task.id, ai_model_id=model.id).one()
    assert grade.grade_name == "Glaucoma"
    assert "AI probability: 0.7700" in (grade.comment or "")
    assert db_session.query(AIInferenceRun).filter_by(task_id=task.id, ai_model_id=model.id).count() == 1


def test_run_task_inference_rejects_encounter_set_task(app, db_session):
    _linked_integration(db_session)
    _ai_system(db_session)
    glaucoma = db_session.query(Disease).filter_by(name="Glaucoma").one()
    lab_unit = db_session.query(LabUnit).filter_by(id=100).one()
    from models import PatientEncounters

    encounter = PatientEncounters(
        name="Encounter Set",
        patient_id="PID-1",
        capture_date="2026-04-18",
        lab_unit_id=lab_unit.id,
    )
    db_session.add(encounter)
    db_session.flush()

    task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
    )
    db_session.add(task)
    db_session.flush()

    result = run_task_inference(task_id=task.id, requested_by_user_id=None, force=False)

    assert result.status == "failed"
    assert result.error_code == "encounter_set_task_not_supported"
