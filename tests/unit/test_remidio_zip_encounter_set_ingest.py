from __future__ import annotations

from io import BytesIO
from uuid import uuid4
import zipfile

from PIL import Image

from models import EncounterSetAttachment, EncounterSetImage, GradingTask, PatientEncounters, Project
from verify_encounter_set.routes import _create_verified_encounter_set_tasks
from zip_processor import ingest_remidio_zip_as_encounter_set


def _jpg_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), color=(255, 0, 0))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def _write_zip(path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def _configure_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr("zip_processor.BASE_DIR", tmp_path)
    monkeypatch.setattr("zip_processor.UPLOAD_DIR", tmp_path / "uploaded")
    monkeypatch.setattr("zip_processor.PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr("zip_processor.PROCESSING_ERROR_DIR", tmp_path / "error")
    monkeypatch.setattr("zip_processor.IMAGE_DIR", tmp_path / "legacy-images")
    monkeypatch.setattr("zip_processor.PDF_DIR", tmp_path / "legacy-pdfs")


def _project(db_session):
    project = Project(title=f"ZIP EncounterSet {uuid4()}", code=f"ZIPES{uuid4().hex[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    return project


def test_remidio_zip_encounter_set_ingest_infers_pristine_from_direct_images(db_session, core_test_data, monkeypatch, tmp_path):
    _configure_dirs(monkeypatch, tmp_path)
    project = _project(db_session)
    zip_path = tmp_path / "uploaded" / "2026_05_25" / f"pristine_{uuid4().hex}.zip"
    _write_zip(
        zip_path,
        {
            "Jane_Doe_MRN123_2026-05-20/right.jpg": _jpg_bytes(),
            "Jane_Doe_MRN123_2026-05-20/report.pdf": b"%PDF-1.4\n%test\n",
        },
    )

    result = ingest_remidio_zip_as_encounter_set(
        zip_path,
        db_session,
        upload_context={
            "hospital_id": core_test_data["hospital"].id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "project_id": project.id,
            "upload_profile_id": None,
            "default_disease_id": core_test_data["dr"].id,
            "camera_id": None,
            "ingest_mode": "encounter_set",
            "target_disease_ids": [core_test_data["dr"].id],
        },
    )

    encounter = db_session.get(PatientEncounters, result["patient_encounter_id"])
    assert encounter.is_set_based is True
    assert encounter.name == "Jane Doe"
    assert encounter.patient_id == "MRN123"
    assert encounter.capture_date == "2026-05-20"
    assert encounter.metadata_json["camera_type"] == "PRISTINE"

    image = db_session.get(EncounterSetImage, result["encounter_set_image_ids"][0])
    assert image.asset_kind == "clinical_image"
    assert image.creates_task is True
    assert image.metadata_json["camera_type"] == "PRISTINE"
    assert (tmp_path / image.folder_rel / image.original_filename).exists()

    attachment = db_session.get(EncounterSetAttachment, result["encounter_set_attachment_ids"][0])
    assert attachment.asset_kind == "pdf"
    assert attachment.creates_task is False
    assert attachment.metadata_json["report_type"] == "pristine_report"


def test_remidio_zip_encounter_set_ingest_infers_fop_from_fop_folder(db_session, core_test_data, monkeypatch, tmp_path):
    _configure_dirs(monkeypatch, tmp_path)
    project = _project(db_session)
    zip_path = tmp_path / "uploaded" / "2026_05_25" / f"fop_{uuid4().hex}.zip"
    _write_zip(
        zip_path,
        {
            "John_Doe_MRN456_2026-05-21/fop/right.jpg": _jpg_bytes(),
            "John_Doe_MRN456_2026-05-21/fop/glaucoma_report.pdf": b"%PDF-1.4\n%test\n",
            "John_Doe_MRN456_2026-05-21/fop/dr_report.pdf": b"%PDF-1.4\n%test\n",
        },
    )

    result = ingest_remidio_zip_as_encounter_set(
        zip_path,
        db_session,
        upload_context={
            "hospital_id": core_test_data["hospital"].id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "project_id": project.id,
            "upload_profile_id": None,
            "default_disease_id": core_test_data["dr"].id,
            "camera_id": None,
            "ingest_mode": "encounter_set",
            "target_disease_ids": [core_test_data["dr"].id, core_test_data["glaucoma"].id],
        },
    )

    encounter = db_session.get(PatientEncounters, result["patient_encounter_id"])
    assert encounter.metadata_json["camera_type"] == "FOP"
    assert set(encounter.metadata_json["report_types"]) == {"fop_dr_report", "fop_glaucoma_report"}

    image = db_session.get(EncounterSetImage, result["encounter_set_image_ids"][0])
    assert image.metadata_json["camera_type"] == "FOP"
    assert len(result["encounter_set_attachment_ids"]) == 2


def test_verified_remidio_zip_encounter_set_creates_target_tasks(db_session, core_test_data):
    encounter = PatientEncounters(
        name="Task Test",
        patient_id=f"MRN{uuid4().hex[:6]}",
        capture_date="2026-05-22",
        lab_unit_id=core_test_data["lab_unit"].id,
        is_set_based=True,
        encounter_verified_status="verified",
    )
    db_session.add(encounter)
    db_session.flush()
    from upload_profiles.models import PatientEncounterTargetDisease

    db_session.add_all(
        [
            PatientEncounterTargetDisease(patient_encounter_id=encounter.id, disease_id=core_test_data["dr"].id),
            PatientEncounterTargetDisease(patient_encounter_id=encounter.id, disease_id=core_test_data["glaucoma"].id),
        ]
    )
    db_session.flush()

    created = _create_verified_encounter_set_tasks(db_session, encounter)

    assert created == 2
    tasks = db_session.query(GradingTask).filter(GradingTask.patient_encounter_id == encounter.id).all()
    assert {task.disease_id for task in tasks} == {core_test_data["dr"].id, core_test_data["glaucoma"].id}
