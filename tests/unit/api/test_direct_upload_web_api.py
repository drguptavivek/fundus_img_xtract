from __future__ import annotations

import io
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
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE


_SEQUENCE = count(1)


def test_direct_upload_page_loads_htmx_shell(client, login_user, direct_upload_web_data):
    login_user(direct_upload_web_data["uploader"].username, "Test@2026")

    response = client.get("/direct/upload")

    assert response.status_code == 200
    assert b'hx-get="/api/direct-uploads/form"' in response.data
    assert b'hx-get="/api/direct-uploads/workspace"' in response.data


def test_direct_upload_form_partial_is_api_rendered(client, login_user, direct_upload_web_data):
    login_user(direct_upload_web_data["uploader"].username, "Test@2026")

    response = client.get("/api/direct-uploads/form")

    assert response.status_code == 200
    assert b'hx-post="/api/direct-uploads/uploads/web"' in response.data
    assert b"data-upload-profile-form" in response.data
    assert direct_upload_web_data["profile"].name.encode() in response.data


def test_direct_upload_web_api_creates_job_and_returns_workspace(client, login_user, direct_upload_web_data):
    login_user(direct_upload_web_data["uploader"].username, "Test@2026")

    response = client.post(
        "/api/direct-uploads/uploads/web",
        data={
            "profile_id": str(direct_upload_web_data["profile"].id),
            "hospital_id": str(direct_upload_web_data["hospital"].id),
            "project_id": str(direct_upload_web_data["project"].id),
            "lab_unit_id": str(direct_upload_web_data["lab"].id),
            "disease_id": str(direct_upload_web_data["disease"].id),
            "camera_id": str(direct_upload_web_data["camera"].id),
            "area_id": str(direct_upload_web_data["area"].id),
            "remarks": "web htmx remarks",
            "files": [(_png_file("web-direct.png"), "web-direct.png")],
        },
        headers={"HX-Request": "true"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"Submitted 1 image" in response.data
    assert b"Upload Status" in response.data


@pytest.fixture
def direct_upload_web_data(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Direct Web Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Direct Web Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Direct Web Project {suffix}", code=f"DIRECT_WEB_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Direct Web Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Direct Web Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(db_session, "fileUploader", username=f"direct_web_uploader_{suffix}", lab_units=[lab])
    profile = UploadProfile(
        name=f"Direct Web Profile {suffix}",
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

def _png_file(filename: str) -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(0, 0, 255)).save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = filename
    return buffer
