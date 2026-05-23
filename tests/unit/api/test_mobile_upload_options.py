from __future__ import annotations

from itertools import count

import pytest

from models import Area, Camera, Disease, Hospital, LabUnit, Project, Role
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileArea,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_PREGRADED, UPLOAD_KIND_REMIDIO
from tests.helpers.factories import UserFactory


JWT_SECRET = "test-mobile-upload-options-secret"
_SEQUENCE = count(1)


@pytest.fixture
def upload_options_data(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Upload Options Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab_a = LabUnit(name=f"Upload Options Lab A {suffix}", hospital_id=hospital.id)
    lab_b = LabUnit(name=f"Upload Options Lab B {suffix}", hospital_id=hospital.id)
    db_session.add_all([lab_a, lab_b])
    db_session.flush()

    glaucoma = db_session.merge(core_test_data["glaucoma"])
    dr = db_session.merge(core_test_data["dr"])
    camera_a = db_session.merge(core_test_data["camera"])
    area_a = db_session.merge(core_test_data["area"])
    camera_b = Camera(name=f"Mobile Options Camera B {suffix}")
    area_b = Area(name=f"Mobile Options Area B {suffix}")
    db_session.add_all([camera_b, area_b])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"mobile_options_uploader_{suffix}",
        lab_units=[lab_a, lab_b],
    )
    no_upload_role_user = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"mobile_options_oph_{suffix}",
        lab_units=[lab_a],
    )
    admin_without_lab = UserFactory.create_by_role(
        db_session,
        "admin",
        username=f"mobile_options_admin_{suffix}",
    )
    elevated_uploader_without_lab = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"mobile_options_elevated_uploader_{suffix}",
    )
    admin_role = db_session.query(Role).filter_by(name="admin").one()
    elevated_uploader_without_lab.roles.append(admin_role)

    project_a = Project(title=f"Mobile Upload Project A {suffix}", code=f"MOBILE_UPLOAD_A_{suffix}", active=True)
    project_b = Project(title=f"Mobile Upload Project B {suffix}", code=f"MOBILE_UPLOAD_B_{suffix}", active=True)
    db_session.add_all([project_a, project_b])
    db_session.flush()

    profile_a = _add_profile(db_session, uploader.id, lab_a.id, project_a.id, glaucoma.id, camera_a.id, area_a.id)
    profile_b = _add_profile(db_session, uploader.id, lab_b.id, project_b.id, dr.id, camera_b.id, area_b.id)
    _add_profile(db_session, admin_without_lab.id, lab_a.id, project_a.id, glaucoma.id, camera_a.id, area_a.id)
    _add_profile(db_session, elevated_uploader_without_lab.id, lab_a.id, project_a.id, glaucoma.id, camera_a.id, area_a.id)
    db_session.flush()

    return {
        "uploader": uploader,
        "no_upload_role_user": no_upload_role_user,
        "admin_without_lab": admin_without_lab,
        "elevated_uploader_without_lab": elevated_uploader_without_lab,
        "glaucoma": glaucoma,
        "dr": dr,
        "camera_a": camera_a,
        "camera_b": camera_b,
        "area_a": area_a,
        "area_b": area_b,
        "lab_a": lab_a,
        "lab_b": lab_b,
        "project_a": project_a,
        "project_b": project_b,
        "profile_a": profile_a,
        "profile_b": profile_b,
    }


def test_mobile_upload_options_requires_token(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)

    response = client.get("/api/mobile/v1/upload-options")

    assert response.status_code == 401


def test_mobile_upload_options_rejects_user_without_file_uploader_role(client, db_session, monkeypatch, upload_options_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, upload_options_data["no_upload_role_user"].username)

    response = client.get("/api/mobile/v1/upload-options", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_mobile_upload_options_returns_empty_arrays_without_valid_profiles(client, db_session, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = UserFactory.create_by_role(db_session, "fileUploader", username="mobile_options_empty")
    db_session.flush()
    token = _mobile_access_token(client, user.username)

    response = client.get("/api/mobile/v1/upload-options", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json() == {
        "projects": [],
        "lab_units": [],
        "diseases": [],
        "cameras": [],
        "areas": [],
        "profiles": [],
    }


def test_mobile_upload_options_admin_has_no_mapping_without_explicit_lab_assignment(
    client,
    db_session,
    monkeypatch,
    upload_options_data,
):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, upload_options_data["elevated_uploader_without_lab"].username)

    response = client.get("/api/mobile/v1/upload-options", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.get_json()["profiles"] == []


def test_mobile_upload_options_filters_keep_option_lists_consistent(client, db_session, monkeypatch, upload_options_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    token = _mobile_access_token(client, upload_options_data["uploader"].username)

    response = client.get(
        f"/api/mobile/v1/upload-options?disease_name=glaucoma&project_id={upload_options_data['project_a'].id}"
        f"&lab_unit_id={upload_options_data['lab_a'].id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["projects"] == [
        {
            "id": upload_options_data["project_a"].id,
            "title": upload_options_data["project_a"].title,
            "code": upload_options_data["project_a"].code,
        }
    ]
    assert payload["lab_units"] == [
        {
            "id": upload_options_data["lab_a"].id,
            "name": upload_options_data["lab_a"].name,
            "hospital_id": upload_options_data["lab_a"].hospital_id,
        }
    ]
    assert payload["diseases"] == [{"id": upload_options_data["glaucoma"].id, "name": upload_options_data["glaucoma"].name}]
    assert payload["cameras"] == [{"id": upload_options_data["camera_a"].id, "name": upload_options_data["camera_a"].name}]
    assert payload["areas"] == [{"id": upload_options_data["area_a"].id, "name": upload_options_data["area_a"].name}]
    assert [item["profile_id"] for item in payload["profiles"]] == [upload_options_data["profile_a"].id]


def test_mobile_upload_options_strips_web_only_pregraded_kind(client, db_session, monkeypatch, upload_options_data):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    upload_options_data["profile_a"].upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_PREGRADED))
    upload_options_data["profile_a"].upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_REMIDIO))
    db_session.flush()
    token = _mobile_access_token(client, upload_options_data["uploader"].username)

    response = client.get("/api/mobile/v1/upload-options", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    profile = next(item for item in response.get_json()["profiles"] if item["profile_id"] == upload_options_data["profile_a"].id)
    assert UPLOAD_KIND_PREGRADED not in profile["upload_kinds"]
    assert profile["upload_kinds"] == [UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_REMIDIO]


def _add_profile(db_session, user_id, lab_unit_id, project_id, disease_id, camera_id, area_id):
    profile = UploadProfile(
        name=f"Mobile profile {user_id}-{project_id}-{lab_unit_id}",
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
    )
    profile.diseases.append(UploadProfileDisease(disease_id=disease_id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera_id))
    profile.areas.append(UploadProfileArea(area_id=area_id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    db_session.add(profile)
    db_session.flush()
    project_profile = ProjectUploadProfile(project_id=project_id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(
        ProjectUploadProfileAssignment(
            project_upload_profile_id=project_profile.id,
            user_id=user_id,
            lab_unit_id=lab_unit_id,
            active=True,
        )
    )
    db_session.flush()
    return profile


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
