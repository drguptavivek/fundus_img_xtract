"""Shared seeding for the field surface tests."""
from datetime import date
from itertools import count
from uuid import uuid4

import pytest

from data_authorization.models import ProjectRoleGrant
from models import (
    Disease,
    EncounterSetImage,
    Hospital,
    LabUnit,
    PatientEncounters,
    Project,
    Role,
)
from tests.helpers.factories import UserFactory, approve_mobile_device

JWT_SECRET = "test-mobile-jwt-secret-32-chars-long"
_SEQUENCE = count(1)
CAPTURE_DATE = date(2026, 8, 20)


def _role(db_session, name):
    role = db_session.query(Role).filter_by(name=name).first()
    if role is None:
        role = Role(name=name)
        db_session.add(role)
        db_session.flush()
    return role


@pytest.fixture
def field_data(db_session):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Field Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Field Lab {suffix}", hospital_id=hospital.id)
    other_lab = LabUnit(name=f"Other Field Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Field Project {suffix}", code=f"FIELD_{suffix}", active=True)
    db_session.add_all([lab, other_lab, project])
    db_session.flush()

    for name in ("DR", "DME", "Glaucoma"):
        if db_session.query(Disease).filter_by(name=name).first() is None:
            db_session.add(Disease(name=name))
    db_session.flush()

    user = UserFactory.create_by_role(
        db_session, "field_optometrist", username=f"field_user_{suffix}"
    )
    user.hospital_id = hospital.id
    user.lab_units.append(lab)
    db_session.flush()
    approve_mobile_device(db_session, user.id, f"device-{user.username}")

    # Scoped to one lab unit, so the other lab's encounters must stay invisible.
    db_session.add(
        ProjectRoleGrant(
            project_id=project.id,
            user_id=user.id,
            role_id=_role(db_session, "field_optometrist").id,
            scope_type="lab_unit",
            lab_unit_id=lab.id,
            active=True,
        )
    )
    db_session.flush()

    encounter = _encounter(db_session, project, lab, suffix, "FIELD-1", "Field Patient One")
    other_encounter = _encounter(
        db_session, project, other_lab, suffix, "FIELD-2", "Out Of Scope Patient"
    )

    return {
        "user": user,
        "hospital": hospital,
        "lab": lab,
        "other_lab": other_lab,
        "project": project,
        "encounter": encounter,
        "other_encounter": other_encounter,
        "capture_date": CAPTURE_DATE,
    }


def _encounter(db_session, project, lab, suffix, patient_id, name):
    encounter = PatientEncounters(
        uuid=str(uuid4()),
        name=name,
        patient_id=patient_id,
        capture_date=CAPTURE_DATE.isoformat(),
        capture_date_dt=CAPTURE_DATE,
        is_set_based=True,
        project_id=project.id,
        lab_unit_id=lab.id,
        encounter_verified_status="pending",
    )
    db_session.add(encounter)
    db_session.flush()

    for position, eye in ((1, "right"), (2, "left")):
        db_session.add(
            EncounterSetImage(
                uuid=str(uuid4()),
                patient_encounter_id=encounter.id,
                spatial_position=position,
                original_filename=f"{patient_id}_{position}.jpg",
                folder_rel=f"field/{suffix}/{patient_id}",
                asset_kind="clinical_image",
                creates_task=True,
                visible_to_grader=True,
                project_id=project.id,
                hospital_id=lab.hospital_id,
                metadata_json={"laterality": eye, "focus": "macula"},
            )
        )
    db_session.flush()
    return encounter


@pytest.fixture
def field_token(client, db_session, field_data, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    user = field_data["user"]
    response = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": user.username,
            "password": "Test@2026",
            "device_id": f"device-{user.username}",
            "device_name": "Field Device",
        },
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["access_token"]


@pytest.fixture
def auth_headers(field_token):
    return {"Authorization": f"Bearer {field_token}"}
