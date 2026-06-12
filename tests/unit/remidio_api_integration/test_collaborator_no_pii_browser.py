from datetime import date
import zipfile
from io import BytesIO
import uuid

import yaml

from models import EncounterSetImage, Hospital, LabUnit, PatientEncounters, Project, ProjectInvestigator, Role, User
from remidio_api_integration import service


def _collaborator(db_session, username: str = "no_pii_collaborator") -> User:
    role = db_session.query(Role).filter_by(name="collaborator").one_or_none()
    if role is None:
        role = Role(name="collaborator")
        db_session.add(role)
        db_session.flush()
    user = User(username=username, password_hash="x", is_active=True, roles=[role])
    db_session.add(user)
    db_session.flush()
    return user


def _project_encounter(db_session, *, code: str, patient_id: str, patient_name: str):
    hospital = Hospital(name=f"Collaborator Browser Hospital {code}")
    lab = LabUnit(name=f"Collaborator Browser Lab {code}", hospital=hospital)
    project = Project(title=f"Collaborator Browser Project {code}", code=code, active=True)
    db_session.add_all([hospital, lab, project])
    db_session.flush()
    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name=patient_name,
        patient_id=patient_id,
        capture_date="2026-06-12",
        capture_date_dt=date(2026, 6, 12),
        lab_unit_id=lab.id,
        project_id=project.id,
        is_set_based=True,
        encounter_verified_status="pending",
        metadata_json={
            "patient": {"patient_name": patient_name, "patient_age_yrs": "63", "sex": "F"},
            "encounter": {"capture_datetime": "2026-06-12T10:15:00+00:00"},
            "remidio_exam_id": "EXAM-PII",
        },
    )
    db_session.add(encounter)
    db_session.flush()
    return project, encounter


def test_no_pii_browser_only_lists_active_collaborator_projects(db_session):
    user = _collaborator(db_session)
    allowed_project, _ = _project_encounter(
        db_session,
        code="COLLABA",
        patient_id="MRN-PII-001",
        patient_name="Patient Pii",
    )
    blocked_project, _ = _project_encounter(
        db_session,
        code="COLLABB",
        patient_id="MRN-PII-002",
        patient_name="Other Patient",
    )
    db_session.add(
        ProjectInvestigator(
            project_id=allowed_project.id,
            user_id=user.id,
            role="collaborator",
            active=True,
        )
    )
    db_session.commit()

    context = service.list_encounter_set_browser(db_session, user=user, no_pii=True)

    assert [project["id"] for project in context["projects"]] == [allowed_project.id]
    assert blocked_project.id not in {project["id"] for project in context["projects"]}


def test_no_pii_browser_redacts_patient_identifiers(db_session):
    user = _collaborator(db_session, username="no_pii_redaction_collaborator")
    project, encounter = _project_encounter(
        db_session,
        code="COLLABC",
        patient_id="MRN-SECRET",
        patient_name="Secret Patient",
    )
    db_session.add(ProjectInvestigator(project_id=project.id, user_id=user.id, role="collaborator", active=True))
    db_session.commit()

    context = service.list_encounter_set_browser(
        db_session,
        user=user,
        project_id=project.id,
        selected_date=date(2026, 6, 12),
        encounter_id=encounter.id,
        no_pii=True,
    )

    assert context["patients"][0]["name"] == f"EncounterSet {encounter.uuid}"
    assert context["patients"][0]["mrn"] is None
    assert context["patients"][0]["age"] is None
    assert context["patients"][0]["sex"] is None
    assert context["detail"]["name"] == f"EncounterSet {encounter.uuid}"
    assert context["detail"]["metadata_patient"] == {}
    assert context["detail"]["metadata_encounter"] == {}
    assert context["detail"]["remidio_exam_id"] is None


def test_no_pii_export_zip_uses_encounter_uuid_not_mrn(db_session, monkeypatch, tmp_path):
    user = _collaborator(db_session, username="no_pii_export_collaborator")
    project, encounter = _project_encounter(
        db_session,
        code="COLLABD",
        patient_id="MRN-ZIP-SECRET",
        patient_name="Zip Secret Patient",
    )
    media_dir = tmp_path / "files" / "export_sets"
    media_dir.mkdir(parents=True)
    (media_dir / "export_image.jpg").write_bytes(b"fake image content")
    image = EncounterSetImage(
        uuid=str(uuid.uuid4()),
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename="export_image.jpg",
        folder_rel="files/export_sets",
        project_id=project.id,
        metadata_json={
            "laterality": "OD",
            "fundus_field": "macula",
            "image_type": "color_fundus",
            "image_variant": "disc",
            "image_segment": "posterior",
            "is_montage": True,
            "width_px": 2048,
            "height_px": 1536,
            "patient_id": "MRN-ZIP-SECRET",
        },
    )
    db_session.add_all(
        [
            ProjectInvestigator(project_id=project.id, user_id=user.id, role="collaborator", active=True),
            image,
        ]
    )
    db_session.commit()
    monkeypatch.setattr(service, "BASE_DIR", tmp_path)

    result = service.build_no_pii_encounter_set_zip(db_session, user=user, encounter_id=encounter.id)

    assert result is not None
    content, filename = result
    assert filename == f"{encounter.uuid}.zip"
    with zipfile.ZipFile(BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert "metadata.yaml" in names
        assert any(name.startswith("images/encounterset_") and name.endswith(".jpg") for name in names)
        metadata = yaml.safe_load(archive.read("metadata.yaml"))

    assert set(metadata) == {"encounter_set", "images"}
    assert set(metadata["encounter_set"]) == {"uuid", "date", "age", "sex", "deviceType"}
    assert metadata["encounter_set"]["uuid"] == encounter.uuid
    assert "mrn" not in metadata["encounter_set"]
    assert "patient_id" not in metadata["encounter_set"]
    assert set(metadata["images"][0]) == {
        "image_uuid",
        "position",
        "laterality",
        "field",
        "type",
        "camera",
        "image_variant",
        "image_segment",
        "is_montage",
        "width_px",
        "height_px",
    }
    assert metadata["images"][0]["laterality"] == "OD"
    assert metadata["images"][0]["position"] == 2
    assert metadata["images"][0]["width_px"] == 2048
    assert metadata["images"][0]["height_px"] == 1536
