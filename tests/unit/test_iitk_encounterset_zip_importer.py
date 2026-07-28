from __future__ import annotations

from io import BytesIO
from uuid import uuid4
import json
import zipfile

from PIL import Image

from encounter_sets.iitk_encounterset_zip_importer import ingest_iitk_encounterset_zip
from models import Disease, EncounterSetImage, PatientEncounters, Project
from encounter_sets.models import EncounterSetAttachment


def _jpg_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), color=(0, 128, 255))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def _metadata(mrn: str, date: str, session_id: str) -> bytes:
    return json.dumps(
        {
            "sessionId": session_id,
            "site": "delhi",
            "mrn": mrn,
            "age": 28,
            "startedAt": f"{date[:4]}-{date[4:6]}-{date[6:8]}T10:13:13.396299",
            "eye": "ou",
            "gender": "male",
            "diagnosis": "strabismus",
            "mode": "standard",
            "capturedPositions": ["primary", "right", "left", "composite"],
            "clinicianUid": "clinician-test",
        }
    ).encode("utf-8")


def _write_iitk_zip(path, encounters: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("New folder/", b"")
        for mrn, date, suffix in encounters:
            folder = f"New folder/MRN{mrn}_{date}_{suffix}"
            archive.writestr(f"{folder}/MRN{mrn}_{date}_metadata.json", _metadata(mrn, date, f"{suffix}-session"))
            for position in ("primary", "right", "left", "composite"):
                archive.writestr(f"{folder}/MRN{mrn}_{date}_{position}.jpg", _jpg_bytes())


def _configure_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr("encounter_sets.iitk_encounterset_zip_importer.BASE_DIR", tmp_path)
    monkeypatch.setattr("encounter_sets.iitk_encounterset_zip_importer.PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr("encounter_sets.iitk_encounterset_zip_importer.PROCESSING_ERROR_DIR", tmp_path / "error")


def _project(db_session):
    project = Project(title=f"IITK ZIP {uuid4()}", code=f"IITK{uuid4().hex[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    return project


def test_iitk_zip_importer_ingests_multiple_encounter_folders(db_session, core_test_data, monkeypatch, tmp_path):
    _configure_dirs(monkeypatch, tmp_path)
    project = _project(db_session)
    strabismus = db_session.query(Disease).filter_by(name="Strabismus").first()
    assert strabismus is not None
    zip_path = tmp_path / "uploaded" / "files_from_iit_kottyam.zip"
    _write_iitk_zip(
        zip_path,
        [
            ("107985017", "20260605", "6a57c452"),
            ("109024080", "20260607", "276e969c"),
        ],
    )

    result = ingest_iitk_encounterset_zip(
        zip_path,
        db_session,
        upload_context={
            "hospital_id": core_test_data["hospital"].id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "project_id": project.id,
            "upload_profile_id": None,
            "camera_id": None,
            "ingest_mode": "encounter_set",
            "encounter_set_zip_format": "iitk",
            "target_disease_ids": [strabismus.id],
        },
    )

    assert result["status"] == "ok"
    assert len(result["patient_encounter_ids"]) == 2
    assert len(result["encounter_set_image_ids"]) == 8
    assert len(result["encounter_set_attachment_ids"]) == 2
    assert not zip_path.exists()

    encounters = (
        db_session.query(PatientEncounters)
        .filter(PatientEncounters.id.in_(result["patient_encounter_ids"]))
        .order_by(PatientEncounters.patient_id)
        .all()
    )
    assert [encounter.patient_id for encounter in encounters] == ["107985017", "109024080"]
    assert all(encounter.is_set_based for encounter in encounters)
    assert encounters[0].metadata_json["source_kind"] == "iitk_zip"
    assert encounters[0].metadata_json["diagnosis"] == "strabismus"

    images = (
        db_session.query(EncounterSetImage)
        .filter(EncounterSetImage.patient_encounter_id == encounters[0].id)
        .order_by(EncounterSetImage.spatial_position)
        .all()
    )
    assert [image.metadata_json["gaze_position"] for image in images] == ["primary", "right", "left", "composite"]
    assert [image.spatial_position for image in images] == [1, 5, 9, 10]
    assert (tmp_path / images[0].folder_rel / images[0].original_filename).exists()

    attachment = (
        db_session.query(EncounterSetAttachment)
        .filter(EncounterSetAttachment.patient_encounter_id == encounters[0].id)
        .one()
    )
    assert attachment.asset_kind == "document"
    assert attachment.mime_type == "application/json"
    assert attachment.metadata_json["document_type"] == "iitk_metadata_json"
