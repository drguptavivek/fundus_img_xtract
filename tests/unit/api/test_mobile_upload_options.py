from __future__ import annotations

from itertools import count

import pytest

from models import Area, Camera, Disease, Hospital, LabUnit, Project, Role, UploadMapping, UploadMappingArea, UploadMappingCamera
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

    mapping_a = _add_mapping(db_session, uploader.id, lab_a.id, project_a.id, glaucoma.id, camera_a.id, area_a.id)
    mapping_b = _add_mapping(db_session, uploader.id, lab_b.id, project_b.id, dr.id, camera_b.id, area_b.id)
    _add_mapping(db_session, admin_without_lab.id, lab_a.id, project_a.id, glaucoma.id, camera_a.id, area_a.id)
    _add_mapping(db_session, elevated_uploader_without_lab.id, lab_a.id, project_a.id, glaucoma.id, camera_a.id, area_a.id)
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
        "mapping_a": mapping_a,
        "mapping_b": mapping_b,
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


def test_mobile_upload_options_returns_empty_arrays_without_valid_mappings(client, db_session, monkeypatch):
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
        "mappings": [],
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
    assert response.get_json()["mappings"] == []


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
    assert [item["mapping_id"] for item in payload["mappings"]] == [upload_options_data["mapping_a"].id]


def _add_mapping(db_session, user_id, lab_unit_id, project_id, disease_id, camera_id, area_id):
    mapping = UploadMapping(
        user_id=user_id,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        disease_id=disease_id,
        default_disease_id=disease_id,
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
    )
    mapping.cameras.append(UploadMappingCamera(camera_id=camera_id))
    mapping.areas.append(UploadMappingArea(area_id=area_id))
    db_session.add(mapping)
    db_session.flush()
    return mapping


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
