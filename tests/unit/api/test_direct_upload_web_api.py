from __future__ import annotations

import io
from itertools import count

import pytest
from PIL import Image

from models import Area, Camera, Hospital, Job, JobItem, LabUnit, Project
from tests.helpers.factories import UserFactory
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileArea,
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
    assert b'data-upload-defaults-storage-key="fundus.directUpload.web.defaults.v1"' in response.data
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
    assert b"Uploaded 1, duplicates 0, rejected 0" in response.data
    assert b"Upload Status" in response.data


def test_direct_upload_web_api_reports_duplicate_counts(client, login_user, db_session, direct_upload_web_data):
    login_user(direct_upload_web_data["uploader"].username, "Test@2026")

    first_response = client.post(
        "/api/direct-uploads/uploads/web",
        data={
            "profile_id": str(direct_upload_web_data["profile"].id),
            "hospital_id": str(direct_upload_web_data["hospital"].id),
            "project_id": str(direct_upload_web_data["project"].id),
            "lab_unit_id": str(direct_upload_web_data["lab"].id),
            "disease_id": str(direct_upload_web_data["disease"].id),
            "camera_id": str(direct_upload_web_data["camera"].id),
            "area_id": str(direct_upload_web_data["area"].id),
            "files": [(_png_file("web-duplicate.png"), "web-duplicate.png")],
        },
        headers={"HX-Request": "true"},
        content_type="multipart/form-data",
    )
    assert first_response.status_code == 200

    duplicate_response = client.post(
        "/api/direct-uploads/uploads/web",
        data={
            "profile_id": str(direct_upload_web_data["profile"].id),
            "hospital_id": str(direct_upload_web_data["hospital"].id),
            "project_id": str(direct_upload_web_data["project"].id),
            "lab_unit_id": str(direct_upload_web_data["lab"].id),
            "disease_id": str(direct_upload_web_data["disease"].id),
            "camera_id": str(direct_upload_web_data["camera"].id),
            "area_id": str(direct_upload_web_data["area"].id),
            "files": [(_png_file("web-duplicate-again.png"), "web-duplicate-again.png")],
        },
        headers={"HX-Request": "true"},
        content_type="multipart/form-data",
    )

    assert duplicate_response.status_code == 200
    assert b"Uploaded 0, duplicates 1, rejected 0" in duplicate_response.data
    assert db_session.query(JobItem).filter_by(state="duplicate").count() == 1


def test_direct_upload_workspace_shows_only_current_user_recent_jobs(client, login_user, db_session, direct_upload_web_data):
    other_user = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"other_direct_web_uploader_{next(_SEQUENCE)}",
        lab_units=[direct_upload_web_data["lab"]],
    )
    current_job = Job(
        token=f"current-direct-{next(_SEQUENCE)}",
        status="completed",
        upload_type="direct image",
        uploader_user_id=direct_upload_web_data["uploader"].id,
        uploader_username=direct_upload_web_data["uploader"].username,
        lab_unit_id=direct_upload_web_data["lab"].id,
        project_id=direct_upload_web_data["project"].id,
    )
    other_job = Job(
        token=f"other-direct-{next(_SEQUENCE)}",
        status="completed",
        upload_type="direct image",
        uploader_user_id=other_user.id,
        uploader_username=other_user.username,
        lab_unit_id=direct_upload_web_data["lab"].id,
        project_id=direct_upload_web_data["project"].id,
    )
    current_job.items.append(JobItem(filename="current.png", state="completed"))
    other_job.items.append(JobItem(filename="other.png", state="completed"))
    db_session.add_all([current_job, other_job])
    db_session.flush()
    login_user(direct_upload_web_data["uploader"].username, "Test@2026")

    response = client.get("/api/direct-uploads/workspace")

    assert response.status_code == 200
    assert current_job.token[:8].encode() in response.data
    assert other_job.token[:8].encode() not in response.data


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
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
    )
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    db_session.add(profile)
    db_session.flush()
    project_profile = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(
        ProjectUploadProfileAssignment(
            project_upload_profile_id=project_profile.id,
            user_id=uploader.id,
            lab_unit_id=lab.id,
            active=True,
        )
    )
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
