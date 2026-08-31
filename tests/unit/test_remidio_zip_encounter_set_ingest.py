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


def test_verified_remidio_zip_encounter_set_creates_target_tasks(app, db_session, core_test_data):
    """Task creation derives from the encounter's upload-profile EncounterSet
    config (grading schemes) and eligible reviewed images — not from bare
    PatientEncounterTargetDisease rows."""
    from datetime import date, datetime

    from encounter_set_types.models import EncounterSetType
    from upload_profiles.models import (
        UploadProfile,
        UploadProfileEncounterSetType,
        UploadProfileEncounterSetTypeImageGradingScheme,
    )

    dr = db_session.merge(core_test_data["dr"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    project = Project(title=f"ZIP Tasks {uuid4()}", code=f"ZIPTASK{uuid4().hex[:8]}", active=True)
    encounter_set_type = EncounterSetType(
        name=f"ZIP Task Set {uuid4().hex[:6]}",
        code=f"ziptask_{uuid4().hex[:8]}",
        metadata_schema_json={"fields": []},
        asset_rules_json={"allow_clinical_images": True},
        active=True,
    )
    upload_profile = UploadProfile(name=f"ZIP Task Profile {uuid4().hex[:6]}", active=True)
    config = UploadProfileEncounterSetType(
        encounter_set_type=encounter_set_type,
        encounter_grading_scheme=dr,
        default_image_grading_scheme=dr,
        image_grading_schemes=[
            UploadProfileEncounterSetTypeImageGradingScheme(
                disease=dr, is_default=True, display_order=1
            ),
            UploadProfileEncounterSetTypeImageGradingScheme(
                disease=glaucoma, is_default=False, display_order=2
            ),
        ],
    )
    upload_profile.encounter_set_types.append(config)
    db_session.add_all([project, encounter_set_type, upload_profile])
    db_session.flush()

    encounter = PatientEncounters(
        name="Task Test",
        patient_id=f"MRN{uuid4().hex[:6]}",
        capture_date="2026-05-22",
        lab_unit_id=core_test_data["lab_unit"].id,
        is_set_based=True,
        encounter_verified_status="verified",
        project_id=project.id,
        upload_profile_id=upload_profile.id,
    )
    db_session.add(encounter)
    db_session.flush()

    image = EncounterSetImage(
        uuid=str(uuid4()),
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="task_test.jpg",
        folder_rel=f"files/test_sets/{encounter.id}",
        metadata_json={"laterality": "right", "image_variant": "STANDARD", "fundus_field": "macula"},
        is_reviewed=True,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        created_at=datetime.now(),
    )
    db_session.add(image)
    db_session.flush()

    created = _create_verified_encounter_set_tasks(db_session, encounter, create_negative_controls=False)

    # The unified package anchors an encounter-level grading task and creates
    # per-disease image tasks. Encounter-level tasks reference the encounter;
    # image-level tasks reference their EncounterSetImage.
    tasks = db_session.query(GradingTask).filter(
        (GradingTask.patient_encounter_id == encounter.id)
        | (GradingTask.encounter_set_image_id == image.id)
    ).all()
    assert created >= 2
    assert {t.disease_id for t in tasks} == {dr.id, glaucoma.id}
    assert all(task.patient_encounter_id == encounter.id for task in tasks if task.grading_target_level == "encounter")
