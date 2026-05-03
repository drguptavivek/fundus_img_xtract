from __future__ import annotations

import io
import json
import zipfile
from itertools import count

import pytest
from PIL import Image

from models import Area, Camera, Hospital, LabUnit, Project
from tests.helpers.factories import UserFactory
from upload_profiles.models import (
    UploadProfile,
    UploadProfileArea,
    UploadProfileAssignment,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_ENCOUNTER_SET, UPLOAD_KIND_REMIDIO


JWT_SECRET = "test-mobile-upload-contract-secret"
_SEQUENCE = count(1)


@pytest.fixture
def mobile_upload_contract_data(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Mobile Contract Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Mobile Contract Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Mobile Contract Project {suffix}", code=f"MOBILE_CONTRACT_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Mobile Contract Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Mobile Contract Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"mobile_contract_uploader_{suffix}",
        lab_units=[lab],
    )
    profile = UploadProfile(
        name=f"Mobile Contract Profile {suffix}",
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
    db_session.add(profile)
    db_session.flush()

    return {
        "uploader": uploader,
        "profile": profile,
        "lab": lab,
        "project": project,
        "disease": disease,
        "camera": camera,
        "area": area,
    }


@pytest.fixture
def mobile_contract_headers(client, monkeypatch, mobile_upload_contract_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, mobile_upload_contract_data["uploader"].username)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def documented_multipart_shapes(mobile_upload_contract_data):
    def direct_image():
        return {
            "profile_id": str(mobile_upload_contract_data["profile"].id),
            "idempotency_key": "contract-direct-idempotency-key",
            "upload_kind": UPLOAD_KIND_DIRECT_IMAGE,
            "project_id": str(mobile_upload_contract_data["project"].id),
            "lab_unit_id": str(mobile_upload_contract_data["lab"].id),
            "disease_id": str(mobile_upload_contract_data["disease"].id),
            "camera_id": str(mobile_upload_contract_data["camera"].id),
            "area_id": str(mobile_upload_contract_data["area"].id),
            "is_mydriatic": "false",
            "remarks": "curl-style direct upload remarks",
            "files": [(_png_file("curl-direct.png"), "curl-direct.png")],
        }

    def remidio():
        return {
            "profile_id": str(mobile_upload_contract_data["profile"].id),
            "idempotency_key": "contract-remidio-idempotency-key",
            "upload_kind": UPLOAD_KIND_REMIDIO,
            "project_id": str(mobile_upload_contract_data["project"].id),
            "lab_unit_id": str(mobile_upload_contract_data["lab"].id),
            "camera_id": str(mobile_upload_contract_data["camera"].id),
            "files": [(_zip_file("Patient_001_20260503/image.jpg"), "curl-remidio.zip")],
        }

    def encounter_set():
        encounter_json = {
            "patient_id": "MRN-CURL-123",
            "patient_name": "Curl Style Patient",
            "capture_date": "2026-05-03",
            "disease_ids": [mobile_upload_contract_data["disease"].id],
            "remarks": "curl-style encounter remarks",
            "items": [
                {
                    "file_key": "right_eye",
                    "spatial_position": 1,
                    "camera_id": mobile_upload_contract_data["camera"].id,
                    "area_id": mobile_upload_contract_data["area"].id,
                    "remarks": "right eye curl remarks",
                },
                {
                    "file_key": "left_eye",
                    "spatial_position": 2,
                    "camera_id": mobile_upload_contract_data["camera"].id,
                    "area_id": mobile_upload_contract_data["area"].id,
                    "remarks": "left eye curl remarks",
                },
            ],
        }
        return {
            "profile_id": str(mobile_upload_contract_data["profile"].id),
            "idempotency_key": "contract-encounter-idempotency-key",
            "upload_kind": UPLOAD_KIND_ENCOUNTER_SET,
            "project_id": str(mobile_upload_contract_data["project"].id),
            "lab_unit_id": str(mobile_upload_contract_data["lab"].id),
            "encounter_json": json.dumps(encounter_json),
            "right_eye": (_png_file("curl-right-eye.png"), "curl-right-eye.png"),
            "left_eye": (_png_file("curl-left-eye.png"), "curl-left-eye.png"),
        }

    return {
        UPLOAD_KIND_DIRECT_IMAGE: direct_image,
        UPLOAD_KIND_REMIDIO: remidio,
        UPLOAD_KIND_ENCOUNTER_SET: encounter_set,
    }


def test_mobile_upload_contract_accepts_documented_multipart_shapes_and_polling(
    client,
    mobile_contract_headers,
    documented_multipart_shapes,
):
    upload_tokens = {}

    for upload_kind, form_factory in documented_multipart_shapes.items():
        response = client.post(
            "/api/mobile/v1/uploads",
            data=form_factory(),
            headers=mobile_contract_headers,
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        payload = response.get_json()
        assert payload["upload_kind"] == upload_kind
        assert payload["upload_token"]
        assert payload["accepted_count"] >= 1
        upload_tokens[upload_kind] = payload["upload_token"]

    for upload_kind, upload_token in upload_tokens.items():
        response = client.get(
            f"/api/mobile/v1/uploads/{upload_token}",
            headers=mobile_contract_headers,
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["upload_kind"] == upload_kind
        assert payload["items"]

    response = client.get(
        f"/api/mobile/v1/uploads/{upload_tokens[UPLOAD_KIND_DIRECT_IMAGE]}/inference",
        headers=mobile_contract_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["status"] in {"not_configured", "pending", "running", "complete", "failed"}


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
    buffer.name = "curl-remidio.zip"
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
