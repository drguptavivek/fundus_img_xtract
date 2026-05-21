import pytest
from uuid import uuid4

from encounter_set_types.service import (
    EncounterSetTypeInput,
    create_encounter_set_type,
    normalize_metadata_schema,
)
from models import Area, Camera, Disease, Hospital, LabUnit, Project, Role, User
from upload_profiles.models import (
    UploadProfile,
    UploadProfileArea,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_ENCOUNTER_SET


@pytest.fixture
def encounter_set_type_scope(db_session):
    suffix = uuid4().hex[:8]
    role = db_session.query(Role).filter_by(name="data_manager").one_or_none() or Role(name="data_manager")
    user = User(username=f"est_manager_{suffix}", full_name="EST Manager", password_hash="x", is_active=True)
    user.roles.append(role)
    hospital = Hospital(name=f"EST Hospital {suffix}")
    lab = LabUnit(name=f"EST Lab {suffix}", hospital=hospital)
    user.lab_units.append(lab)
    project = Project(title=f"EST Project {suffix}", code=f"EST_{suffix}", active=True)
    disease = Disease(name=f"Fundus Evaluation {suffix}")
    camera = Camera(name=f"EST Camera {suffix}")
    area = Area(name=f"EST Area {suffix}")
    db_session.add_all([role, user, hospital, lab, project, disease, camera, area])
    db_session.flush()

    profile = UploadProfile(
        name="EST Profile",
        lab_unit_id=lab.id,
        project_id=project.id,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
        active=True,
    )
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=False))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_ENCOUNTER_SET))
    db_session.add(profile)
    db_session.flush()
    return {
        "user": user,
        "project": project,
        "disease": disease,
        "suffix": suffix,
    }


def _valid_schema():
    return {
        "fields": [
            {
                "key": "project_participant_id",
                "label": "Project Unique ID",
                "scope": "encounter",
                "type": "text",
                "required_at_upload": True,
                "required_for_verification": True,
                "visible_to_grader": True,
                "is_pii": False,
            },
            {
                "key": "eye_laterality",
                "label": "Eye",
                "scope": "image",
                "type": "select",
                "selection_mode": "single",
                "options": ["OD", "OS"],
                "required_for_verification": True,
            },
        ]
    }


def test_normalize_metadata_schema_accepts_select_options_and_defaults():
    schema = normalize_metadata_schema(_valid_schema())

    assert schema["fields"][1]["options"] == [
        {"value": "OD", "label": "OD"},
        {"value": "OS", "label": "OS"},
    ]
    assert schema["fields"][1]["required_at_upload"] is False
    assert schema["fields"][1]["selection_mode"] == "single"


def test_normalize_metadata_schema_allows_same_key_in_different_scopes():
    schema = normalize_metadata_schema(
        {
            "fields": [
                {"key": "remarks", "label": "Remarks", "scope": "encounter", "type": "textarea"},
                {"key": "remarks", "label": "Image Remarks", "scope": "image", "type": "textarea"},
            ]
        }
    )

    assert len(schema["fields"]) == 2


def test_normalize_metadata_schema_rejects_duplicate_key_per_scope():
    with pytest.raises(ValueError, match="duplicates key"):
        normalize_metadata_schema(
            {
                "fields": [
                    {"key": "remarks", "label": "Remarks", "scope": "encounter", "type": "textarea"},
                    {"key": "remarks", "label": "More Remarks", "scope": "encounter", "type": "textarea"},
                ]
            }
        )


def test_create_encounter_set_type_scoped_to_manager_project(db_session, encounter_set_type_scope):
    result = create_encounter_set_type(
        encounter_set_type_scope["user"].id,
        EncounterSetTypeInput(
            project_id=encounter_set_type_scope["project"].id,
            name="Fundus Quick Set",
            code=f"fundus_quick_{encounter_set_type_scope['suffix']}",
            description="Fast upload, verification later",
            target_scheme_id=encounter_set_type_scope["disease"].id,
            metadata_schema_json=_valid_schema(),
        ),
    )

    assert result.success is True
    payload = result.payload["encounter_set_type"]
    assert payload["code"] == f"fundus_quick_{encounter_set_type_scope['suffix']}"
    assert payload["created_by_user_id"] == encounter_set_type_scope["user"].id


def test_encounter_set_type_api_create_and_get(client, db_session, encounter_set_type_scope):
    user = encounter_set_type_scope["user"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True

    response = client.post(
        "/api/encounter-set-types",
        json={
            "project_id": encounter_set_type_scope["project"].id,
            "name": "Fundus API Set",
            "code": f"fundus_api_{encounter_set_type_scope['suffix']}",
            "target_scheme_id": encounter_set_type_scope["disease"].id,
            "metadata_schema_json": _valid_schema(),
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    type_id = payload["encounter_set_type"]["id"]

    get_response = client.get(f"/api/encounter-set-types/{type_id}")
    assert get_response.status_code == 200
    assert get_response.get_json()["encounter_set_type"]["code"] == f"fundus_api_{encounter_set_type_scope['suffix']}"


def test_encounter_set_type_api_rejects_invalid_schema(client, encounter_set_type_scope):
    user = encounter_set_type_scope["user"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True

    response = client.post(
        "/api/encounter-set-types",
        json={
            "project_id": encounter_set_type_scope["project"].id,
            "name": "Bad API Set",
            "code": f"bad_api_{encounter_set_type_scope['suffix']}",
            "target_scheme_id": encounter_set_type_scope["disease"].id,
            "metadata_schema_json": {
                "fields": [
                    {
                        "key": "sex",
                        "label": "Sex",
                        "scope": "encounter",
                        "type": "select",
                        "selection_mode": "many",
                    }
                ]
            },
        },
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False
