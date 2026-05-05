from __future__ import annotations

import io
import json
import zipfile
from itertools import count

import pytest
from PIL import Image

from models import (
    AIInferenceRun,
    AIModel,
    AIModelIntegration,
    Area,
    Camera,
    Disease,
    DirectImageUpload,
    EncounterSetImage,
    GradingTask,
    Hospital,
    Job,
    JobItem,
    LabUnit,
    PatientEncounters,
    Project,
)
from upload_profiles.models import (
    UploadProfile,
    UploadProfileArea,
    UploadProfileAssignment,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)
from upload_profiles.service import (
    UPLOAD_KIND_DIRECT_IMAGE,
    UPLOAD_KIND_ENCOUNTER_SET,
    UPLOAD_KIND_PREGRADED,
    UPLOAD_KIND_REMIDIO,
)
from tests.helpers.factories import UserFactory
from utils.fileUtils import abs_from_parts, get_thumbnail_path_direct


JWT_SECRET = "test-mobile-uploads-secret-32-chars"
_SEQUENCE = count(1)


@pytest.fixture
def mobile_upload_data(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Mobile Upload Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Mobile Upload Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"EIM Upload Project {suffix}", code=f"EIM_UPLOAD_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Mobile Upload Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Mobile Upload Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"mobile_uploads_user_{suffix}",
        lab_units=[lab],
    )
    profile = UploadProfile(
        name=f"EIM Mobile Profile {suffix}",
        lab_unit_id=lab.id,
        project_id=project.id,
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
    )
    profile.assignments.append(UploadProfileAssignment(user_id=uploader.id, active=True))
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_REMIDIO))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_ENCOUNTER_SET))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_PREGRADED))
    db_session.add(profile)
    db_session.flush()

    return {
        "uploader": uploader,
        "profile": profile,
        "hospital": hospital,
        "lab": lab,
        "project": project,
        "disease": disease,
        "camera": camera,
        "area": area,
    }


def test_mobile_upload_rejects_pregraded_kind(client, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)

    response = client.post(
        "/api/mobile/v1/uploads",
        data={
            "profile_id": str(mobile_upload_data["profile"].id),
            "idempotency_key": "pregraded-idempotency-key",
            "upload_kind": UPLOAD_KIND_PREGRADED,
            "project_id": str(mobile_upload_data["project"].id),
            "lab_unit_id": str(mobile_upload_data["lab"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "unsupported_upload_kind"


def test_mobile_direct_upload_creates_job_and_stores_plain_text_remarks(client, db_session, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)
    client.application.config["WTF_CSRF_ENABLED"] = True

    response = client.post(
        "/api/mobile/v1/uploads",
        data={
            "profile_id": str(mobile_upload_data["profile"].id),
            "idempotency_key": "direct-idempotency-key",
            "upload_kind": UPLOAD_KIND_DIRECT_IMAGE,
            "project_id": str(mobile_upload_data["project"].id),
            "lab_unit_id": str(mobile_upload_data["lab"].id),
            "disease_id": str(mobile_upload_data["disease"].id),
            "camera_id": str(mobile_upload_data["camera"].id),
            "area_id": str(mobile_upload_data["area"].id),
            "remarks": "patient reported blurred vision",
            "files": [(_png_file("direct-eye.png"), "direct-eye.png")],
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["upload_kind"] == UPLOAD_KIND_DIRECT_IMAGE
    assert payload["accepted_count"] == 1
    assert payload["upload_token"]

    upload = db_session.query(DirectImageUpload).one()
    assert upload.remarks == "patient reported blurred vision"

    status_response = client.get(
        f"/api/mobile/v1/uploads/{payload['upload_token']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_response.status_code == 200
    status_payload = status_response.get_json()
    assert status_payload["items"][0]["source_type"] == "direct_image"
    thumbnail_url = status_payload["items"][0]["thumbnail_url"]
    assert thumbnail_url.startswith(f"/api/mobile/v1/uploads/{payload['upload_token']}/images/")

    thumbnail_response = client.get(
        thumbnail_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert thumbnail_response.status_code == 200
    assert thumbnail_response.content_type.startswith("image/")

    source_path = abs_from_parts(upload.folder_rel, upload.filename, "orig")
    thumbnail_path = get_thumbnail_path_direct(upload.folder_rel, upload.filename, "orig")
    source_path.unlink(missing_ok=True)
    thumbnail_path.unlink(missing_ok=True)
    missing_file_status_response = client.get(
        f"/api/mobile/v1/uploads/{payload['upload_token']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing_file_status_response.status_code == 200
    assert missing_file_status_response.get_json()["items"][0]["thumbnail_url"] is None

    replay_response = client.post(
        "/api/mobile/v1/uploads",
        data={
            "profile_id": str(mobile_upload_data["profile"].id),
            "idempotency_key": "direct-idempotency-key",
            "upload_kind": UPLOAD_KIND_DIRECT_IMAGE,
            "project_id": str(mobile_upload_data["project"].id),
            "lab_unit_id": str(mobile_upload_data["lab"].id),
            "disease_id": str(mobile_upload_data["disease"].id),
            "camera_id": str(mobile_upload_data["camera"].id),
            "area_id": str(mobile_upload_data["area"].id),
            "files": [(_png_file("direct-eye-retry.png"), "direct-eye-retry.png")],
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )

    assert replay_response.status_code == 200
    assert replay_response.get_json()["upload_token"] == payload["upload_token"]
    assert db_session.query(Job).count() == 1
    assert db_session.query(DirectImageUpload).count() == 1

    lookup_response = client.get(
        "/api/mobile/v1/uploads/by-idempotency-key/direct-idempotency-key",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert lookup_response.status_code == 200
    assert lookup_response.get_json()["upload_token"] == payload["upload_token"]


def test_mobile_remidio_upload_accepts_zip_and_creates_queued_job(client, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)

    response = client.post(
        "/api/mobile/v1/uploads",
        data={
            "profile_id": str(mobile_upload_data["profile"].id),
            "idempotency_key": "remidio-idempotency-key",
            "upload_kind": UPLOAD_KIND_REMIDIO,
            "project_id": str(mobile_upload_data["project"].id),
            "lab_unit_id": str(mobile_upload_data["lab"].id),
            "camera_id": str(mobile_upload_data["camera"].id),
            "files": [(_zip_file("Patient_001_20260503/image.jpg"), "remidio.zip")],
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["upload_kind"] == UPLOAD_KIND_REMIDIO
    assert payload["accepted_count"] == 1
    assert payload["status"] == "queued"


def test_mobile_encounter_set_bundle_creates_one_encounter_with_multiple_images(client, db_session, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)
    encounter_json = {
        "patient_id": "MRN-123",
        "patient_name": "Mobile Patient",
        "capture_date": "2026-05-03",
        "disease_ids": [mobile_upload_data["disease"].id],
        "remarks": "encounter level text",
        "items": [
            {
                "file_key": "right_eye",
                "spatial_position": 1,
                "camera_id": mobile_upload_data["camera"].id,
                "area_id": mobile_upload_data["area"].id,
                "remarks": "right eye text",
            },
            {
                "file_key": "left_eye",
                "spatial_position": 2,
                "camera_id": mobile_upload_data["camera"].id,
                "area_id": mobile_upload_data["area"].id,
                "remarks": "left eye text",
            },
        ],
    }

    response = client.post(
        "/api/mobile/v1/uploads",
        data={
            "profile_id": str(mobile_upload_data["profile"].id),
            "idempotency_key": "encounter-idempotency-key",
            "upload_kind": UPLOAD_KIND_ENCOUNTER_SET,
            "project_id": str(mobile_upload_data["project"].id),
            "lab_unit_id": str(mobile_upload_data["lab"].id),
            "encounter_json": json.dumps(encounter_json),
            "right_eye": (_png_file("right-eye.png"), "right-eye.png"),
            "left_eye": (_png_file("left-eye.png"), "left-eye.png"),
        },
        headers={"Authorization": f"Bearer {token}"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["upload_kind"] == UPLOAD_KIND_ENCOUNTER_SET
    assert payload["accepted_count"] == 2

    encounter = db_session.query(PatientEncounters).one()
    assert encounter.patient_id == "MRN-123"
    assert encounter.remarks == "encounter level text"
    assert db_session.query(EncounterSetImage).count() == 2
    assert {image.remarks for image in db_session.query(EncounterSetImage).all()} == {"right eye text", "left eye text"}


def test_mobile_upload_inference_returns_not_configured(client, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)
    client.application.config["WTF_CSRF_ENABLED"] = True
    job = Job(
        token="mobile-inference-token",
        status="completed",
        upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
        upload_profile_id=mobile_upload_data["profile"].id,
        uploader_user_id=mobile_upload_data["uploader"].id,
        lab_unit_id=mobile_upload_data["lab"].id,
        project_id=mobile_upload_data["project"].id,
    )
    from db_transaction_manager import transaction_scope

    with transaction_scope() as db:
        db.add(job)
        db.flush()

    response = client.get(
        "/api/mobile/v1/uploads/mobile-inference-token/inference",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "not_configured"


def test_mobile_upload_inference_returns_image_wise_status(client, db_session, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)
    job = _mobile_inference_job(db_session, mobile_upload_data)
    success_task = _direct_image_task(db_session, mobile_upload_data, filename="success.jpg")
    pending_task = _direct_image_task(db_session, mobile_upload_data, filename="pending.jpg")
    failed_task = _direct_image_task(db_session, mobile_upload_data, filename="failed.jpg")
    model, integration = _wadhwani_model(db_session)
    db_session.add_all(
        [
            JobItem(
                job=job,
                filename="success.jpg",
                state="ok",
                source_type="direct_image",
                source_id=success_task.direct_image_upload_id,
                source_uuid=success_task.direct_image.uuid,
                task_id=success_task.id,
            ),
            JobItem(
                job=job,
                filename="pending.jpg",
                state="ok",
                source_type="direct_image",
                source_id=pending_task.direct_image_upload_id,
                source_uuid=pending_task.direct_image.uuid,
                task_id=pending_task.id,
            ),
            JobItem(
                job=job,
                filename="failed.jpg",
                state="ok",
                source_type="direct_image",
                source_id=failed_task.direct_image_upload_id,
                source_uuid=failed_task.direct_image.uuid,
                task_id=failed_task.id,
            ),
            AIInferenceRun(
                task_id=success_task.id,
                ai_model_id=model.id,
                integration_id=integration.id,
                source="mobile",
                status="success",
                prediction_id="prediction-success",
                execute_response_json={"results": [{"predicted_class_name": "Glaucoma Present", "model_score": 0.71}]},
            ),
            AIInferenceRun(
                task_id=failed_task.id,
                ai_model_id=model.id,
                integration_id=integration.id,
                source="mobile",
                status="failed",
                error_code="execute_failed",
                error_message="Remote Wadhwani API failed.",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/api/mobile/v1/uploads/{job.token}/inference",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "pending"
    by_filename = {item["filename"]: item for item in payload["items"]}
    assert by_filename["success.jpg"]["inference"]["status"] == "success"
    assert by_filename["pending.jpg"]["inference"]["status"] == "pending"
    assert by_filename["failed.jpg"]["inference"]["status"] == "failed"
    assert by_filename["failed.jpg"]["inference"]["error_message"] == "Remote Wadhwani API failed."


def test_mobile_upload_inference_retry_queues_specific_failed_image(client, db_session, monkeypatch, mobile_upload_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_data["uploader"].username)
    captured = {}
    monkeypatch.setattr(
        "services.uploads.mobile.enqueue_task",
        lambda task_name, job_token, task_ids, user_id=None: captured.update(
            task_name=task_name,
            job_token=job_token,
            task_ids=task_ids,
            user_id=user_id,
        ),
    )
    job = _mobile_inference_job(db_session, mobile_upload_data)
    failed_task = _direct_image_task(db_session, mobile_upload_data, filename="failed.jpg")
    other_failed_task = _direct_image_task(db_session, mobile_upload_data, filename="other-failed.jpg")
    model, integration = _wadhwani_model(db_session)
    for task in (failed_task, other_failed_task):
        db_session.add(
            JobItem(
                job=job,
                filename=task.direct_image.filename,
                state="ok",
                source_type="direct_image",
                source_id=task.direct_image_upload_id,
                source_uuid=task.direct_image.uuid,
                task_id=task.id,
            )
        )
        db_session.add(
            AIInferenceRun(
                task_id=task.id,
                ai_model_id=model.id,
                integration_id=integration.id,
                source="mobile",
                status="failed",
                error_code="execute_failed",
                error_message="Remote Wadhwani API failed.",
            )
        )
    db_session.commit()

    response = client.post(
        f"/api/mobile/v1/uploads/{job.token}/inference/retry",
        json={"task_ids": [failed_task.id]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["queued_task_ids"] == [failed_task.id]
    assert captured["task_name"] == "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task"
    assert captured["task_ids"] == [failed_task.id]
    assert captured["user_id"] == mobile_upload_data["uploader"].id


def _png_file(filename: str) -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = filename
    return buffer


def _zip_file(inner_name: str) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(inner_name, b"\xff\xd8\xff\xe0" + b"0" * 20)
    buffer.seek(0)
    buffer.name = "remidio.zip"
    return buffer


def _mobile_access_token(client, username: str) -> str:
    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": username,
            "password": "Test@2026",
            "device_id": f"device-{username}",
            "device_name": "Mobile Device",
        },
    )
    assert response.status_code == 200
    return response.get_json()["access_token"]


def _mobile_inference_job(db_session, mobile_upload_data):
    job = Job(
        token=f"mobile-inference-token-{next(_SEQUENCE)}",
        status="done",
        upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
        upload_profile_id=mobile_upload_data["profile"].id,
        uploader_user_id=mobile_upload_data["uploader"].id,
        uploader_username=mobile_upload_data["uploader"].username,
        lab_unit_id=mobile_upload_data["lab"].id,
        project_id=mobile_upload_data["project"].id,
    )
    db_session.add(job)
    db_session.flush()
    return job


def _direct_image_task(db_session, mobile_upload_data, *, filename: str):
    image = DirectImageUpload(
        original_filename=filename,
        filename=filename,
        folder_rel="test-mobile-inference",
        file_hash=f"hash-{next(_SEQUENCE)}",
        uploader_id=mobile_upload_data["uploader"].id,
        hospital_id=mobile_upload_data["hospital"].id,
        lab_unit_id=mobile_upload_data["lab"].id,
        project_id=mobile_upload_data["project"].id,
        camera_id=mobile_upload_data["camera"].id,
        disease_id=mobile_upload_data["disease"].id,
        area_id=mobile_upload_data["area"].id,
    )
    db_session.add(image)
    db_session.flush()
    task = GradingTask(
        direct_image_upload_id=image.id,
        disease_id=mobile_upload_data["disease"].id,
        lab_unit_id=mobile_upload_data["lab"].id,
    )
    db_session.add(task)
    db_session.flush()
    return task


def _wadhwani_model(db_session):
    model = AIModel(name=f"Wadhwani Test {next(_SEQUENCE)}", version="1")
    db_session.add(model)
    db_session.flush()
    integration = AIModelIntegration(
        ai_model_id=model.id,
        provider="wadhwani_glaucoma",
        client_id="client",
        bearer_token="token",
    )
    db_session.add(integration)
    db_session.flush()
    return model, integration
