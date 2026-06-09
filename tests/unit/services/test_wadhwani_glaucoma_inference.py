from pathlib import Path
from datetime import date
from uuid import uuid4

import requests

from models import (
    AIInferenceRun,
    AIModel,
    AIModelIntegration,
    DIRECT_UPLOAD_DIR,
    Disease,
    DirectImageUpload,
    EncounterSetImage,
    Grade,
    GradingTask,
    LabUnit,
    PatientEncounters,
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


def _encounter_set_image_task(db_session, tmp_path):
    glaucoma = db_session.query(Disease).filter_by(name="Glaucoma").one()
    lab_unit = db_session.query(LabUnit).filter_by(id=100).one()
    encounter = PatientEncounters(
        name="Wadhwani EncounterSet",
        patient_id="internal-mrn-not-sent",
        capture_date="2026-05-14",
        capture_date_dt=date(2026, 5, 14),
        is_set_based=True,
        lab_unit_id=lab_unit.id,
        metadata_json={
            "patient": {
                "patient_age_yrs": 61,
                "sex": "female",
                "patient_dob": "1965-01-01",
                "patient_name": "Do Not Send",
            },
            "encounter": {
                "capture_datetime": "2026-05-14T09:30:00Z",
                "device_type": "Remidio FOP",
            },
        },
    )
    db_session.add(encounter)
    db_session.flush()

    folder_rel = str(tmp_path / f"encounter_set_wadhwani_{uuid4().hex[:8]}")
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename="encounter-set-image.jpg",
        folder_rel=folder_rel,
        hospital_id=lab_unit.hospital_id,
        camera_id=1,
        is_mydriatic=False,
        metadata_json={
            "laterality": "OD",
            "fundus_field": "macula",
            "image_segment": "disc",
            "image_device_type": "FOP NM10",
            "image_bucket": "fundus",
            "image_variant": "original",
            "image_capture_datetime": "2026-05-14T09:31:00Z",
            "remidio_image_quality": "Good",
            "disc_present": True,
            "disc_quality_acceptable": True,
            "disc_quality_score": 0.91,
            "width_px": 2048,
            "height_px": 2048,
        },
    )
    db_session.add(image)
    db_session.flush()

    image_dir = Path(folder_rel)
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / image.original_filename).write_bytes(b"fake-encounter-set-image-bytes")

    task = GradingTask(
        encounter_set_image_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        grading_target_level="image",
        task_source="encounter_set_ai_inference",
    )
    db_session.add(task)
    db_session.flush()
    return task


def _minimal_encounter_set_image_task(db_session, tmp_path):
    glaucoma = db_session.query(Disease).filter_by(name="Glaucoma").one()
    lab_unit = db_session.query(LabUnit).filter_by(id=100).one()
    encounter = PatientEncounters(
        name="Minimal Wadhwani EncounterSet",
        patient_id="internal-mrn-not-sent",
        capture_date="2026-05-14",
        capture_date_dt=date(2026, 5, 14),
        is_set_based=True,
        lab_unit_id=lab_unit.id,
        metadata_json={"patient": {"patient_age_yrs": 61}},
    )
    db_session.add(encounter)
    db_session.flush()

    folder_rel = str(tmp_path / f"encounter_set_wadhwani_minimal_{uuid4().hex[:8]}")
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="minimal-encounter-set-image.jpg",
        folder_rel=folder_rel,
        hospital_id=lab_unit.hospital_id,
        camera_id=None,
        metadata_json={},
    )
    db_session.add(image)
    db_session.flush()

    image_dir = Path(folder_rel)
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / image.original_filename).write_bytes(b"fake-minimal-encounter-set-image-bytes")

    task = GradingTask(
        encounter_set_image_id=image.id,
        disease_id=glaucoma.id,
        lab_unit_id=lab_unit.id,
        grading_target_level="image",
        task_source="encounter_set_ai_inference",
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


def test_run_task_inference_sends_curated_encounter_set_image_metadata(app, db_session, monkeypatch, tmp_path):
    model, _integration = _linked_integration(db_session)
    task = _encounter_set_image_task(db_session, tmp_path)
    _ai_system(db_session)
    executed = {}

    monkeypatch.setattr(
        "services.wadhwani_glaucoma_inference.initialize_prediction",
        lambda **kwargs: {
            "prediction_id": "pred-encounter-set",
            "results": [{"upload_url": "https://upload.example/encounter-set"}],
        },
    )
    monkeypatch.setattr("services.wadhwani_glaucoma_inference.upload_prediction_file", lambda **kwargs: None)

    def capture_execute(**kwargs):
        executed["manifest"] = kwargs["manifest"][0]
        return {
            "prediction_id": "pred-encounter-set",
            "external_request_id": kwargs["external_request_id"],
            "results": [
                {
                    "prediction": "non_referrable",
                    "model_score": 0.12,
                    "confidence": 0.88,
                    "predicted_class": 0,
                    "predicted_class_name": "No Glaucoma",
                }
            ],
        }

    monkeypatch.setattr("services.wadhwani_glaucoma_inference.execute_prediction", capture_execute)

    result = run_task_inference(task_id=task.id, requested_by_user_id=None, force=False)

    assert result.status == "success", result.message
    manifest = executed["manifest"]
    assert manifest["encounter_set_id"]
    assert manifest["patient_age_yrs"] == 61
    assert manifest["sex"] == "female"
    assert manifest["camera_type"] == "Remedio FOP"
    assert manifest["encounter_device_type"] == "Remidio FOP"
    assert manifest["image_device_type"] == "FOP NM10"
    assert manifest["image_type"] == "macula"
    assert manifest["spatial_position"] == 2
    assert manifest["laterality"] == "right"
    assert manifest["fundus_field"] == "macula"
    assert manifest["image_segment"] == "disc"
    assert manifest["image_variant"] == "original"
    assert manifest["remidio_image_quality"] == "Good"
    assert manifest["disc_present"] is True
    assert manifest["disc_quality_acceptable"] is True
    assert manifest["disc_quality_score"] == 0.91
    assert manifest["width_px"] == 2048
    assert manifest["height_px"] == 2048
    assert "patient_dob" not in manifest
    assert "patient_name" not in manifest
    assert "patient_id" not in manifest

    run = db_session.query(AIInferenceRun).filter_by(task_id=task.id, ai_model_id=model.id).one()
    assert run.request_manifest_json == manifest


def test_run_task_inference_omits_absent_encounter_set_image_metadata(app, db_session, monkeypatch, tmp_path):
    _model, _integration = _linked_integration(db_session)
    task = _minimal_encounter_set_image_task(db_session, tmp_path)
    _ai_system(db_session)
    executed = {}

    monkeypatch.setattr(
        "services.wadhwani_glaucoma_inference.initialize_prediction",
        lambda **kwargs: {
            "prediction_id": "pred-minimal-encounter-set",
            "results": [{"upload_url": "https://upload.example/minimal-encounter-set"}],
        },
    )
    monkeypatch.setattr("services.wadhwani_glaucoma_inference.upload_prediction_file", lambda **kwargs: None)

    def capture_execute(**kwargs):
        executed["manifest"] = kwargs["manifest"][0]
        return {
            "prediction_id": "pred-minimal-encounter-set",
            "external_request_id": kwargs["external_request_id"],
            "results": [
                {
                    "prediction": "non_referrable",
                    "model_score": 0.12,
                    "confidence": 0.88,
                    "predicted_class": 0,
                    "predicted_class_name": "No Glaucoma",
                }
            ],
        }

    monkeypatch.setattr("services.wadhwani_glaucoma_inference.execute_prediction", capture_execute)

    result = run_task_inference(task_id=task.id, requested_by_user_id=None, force=False)

    assert result.status == "success", result.message
    manifest = executed["manifest"]
    assert manifest["patient_age_yrs"] == 61
    assert manifest["spatial_position"] == 1
    assert "fundus_field" not in manifest
    assert "image_segment" not in manifest
    assert "remidio_image_quality" not in manifest
    assert "width_px" not in manifest
    assert "height_px" not in manifest
    assert "disc_present" not in manifest
    assert "disc_quality_acceptable" not in manifest
    assert "image_variant" not in manifest


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


def test_run_task_inference_marks_request_exception_failed(app, db_session, monkeypatch):
    model, _integration = _linked_integration(db_session)
    task = _direct_task(db_session)
    _ai_system(db_session)

    def raise_connection_error(**kwargs):
        raise requests.ConnectionError("DNS failed")

    monkeypatch.setattr(
        "services.wadhwani_glaucoma_inference.initialize_prediction",
        raise_connection_error,
    )

    result = run_task_inference(task_id=task.id, requested_by_user_id=None, force=False)

    assert result.status == "failed"
    assert result.error_code == "request_failed"
    db_session.expire_all()
    run = db_session.query(AIInferenceRun).filter_by(task_id=task.id, ai_model_id=model.id).one()
    assert run.status == "failed"
    assert run.error_code == "request_failed"
    assert "DNS failed" in (run.error_message or "")


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
