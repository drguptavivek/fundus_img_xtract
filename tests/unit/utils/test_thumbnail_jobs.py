import pytest

from models import EncounterFile, PatientEncounters, ZipFile
from tests.helpers.factories import ImageFactory
from utils.thumbnail_jobs import schedule_direct_upload_thumbnails, schedule_encounter_thumbnails


def _create_encounter_file(db_session, *, core_test_data, filename, thumbnail_filename=None):
    lab_unit = core_test_data["lab_unit"]
    hospital = core_test_data["hospital"]
    disease = core_test_data["glaucoma"]

    zip_file = ZipFile(
        zip_filename=f"test-{filename}.zip",
        md5_hash=f"md5-{filename}",
    )
    db_session.add(zip_file)
    db_session.flush()

    encounter = PatientEncounters(
        zip_file_id=zip_file.id,
        name=f"Patient {filename}",
        patient_id=f"PID-{filename}",
        capture_date="2024-01-01",
        lab_unit_id=lab_unit.id,
        disease_id=disease.id,
    )
    db_session.add(encounter)
    db_session.flush()

    encounter_file = EncounterFile(
        patient_encounter_id=encounter.id,
        filename=filename,
        file_type="image",
        lab_unit_id=lab_unit.id,
        hospital_id=hospital.id,
        thumbnail_filename=thumbnail_filename,
    )
    db_session.add(encounter_file)
    db_session.flush()
    return encounter_file


def test_schedule_encounter_thumbnails_skips_existing(db_session, app, core_test_data, monkeypatch):
    missing_thumb = _create_encounter_file(
        db_session,
        core_test_data=core_test_data,
        filename="missing_thumb.jpg",
        thumbnail_filename=None,
    )
    existing_thumb = _create_encounter_file(
        db_session,
        core_test_data=core_test_data,
        filename="has_thumb.jpg",
        thumbnail_filename="thm_has_thumb.jpg",
    )
    db_session.commit()

    captured = {}

    def fake_create_thumbnail_job(job_type, image_references, **_kwargs):
        captured["refs"] = image_references
        return "job-token"

    def fake_queue_thumbnail_job(*_args, **_kwargs):
        captured["queued"] = True

    import utils.thumbnail_jobs as thumbnail_jobs

    monkeypatch.setattr(thumbnail_jobs, "create_thumbnail_job", fake_create_thumbnail_job)
    monkeypatch.setattr(thumbnail_jobs, "queue_thumbnail_job", fake_queue_thumbnail_job)

    schedule_encounter_thumbnails([missing_thumb.id, existing_thumb.id], app, user_context={})

    assert captured.get("queued") is True
    assert captured.get("refs") == [{"image_id": missing_thumb.id}]


def test_schedule_direct_upload_thumbnails_skips_existing(db_session, app, core_test_data, monkeypatch):
    lab_unit = core_test_data["lab_unit"]
    hospital = core_test_data["hospital"]

    direct_upload = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=hospital.id,
        lab_unit_id=lab_unit.id,
        filename="direct_img.jpg",
    )
    direct_upload.thumbnail_filename = "thm_direct_img.jpg"
    direct_upload.edited_filename = "direct_img_edited.jpg"
    direct_upload.edited_thumbnail_filename = "thm_direct_img_edited.jpg"
    db_session.commit()

    called = {"create": 0, "queue": 0}

    def fake_create_thumbnail_job(*_args, **_kwargs):
        called["create"] += 1
        return "job-token"

    def fake_queue_thumbnail_job(*_args, **_kwargs):
        called["queue"] += 1

    import utils.thumbnail_jobs as thumbnail_jobs

    monkeypatch.setattr(thumbnail_jobs, "create_thumbnail_job", fake_create_thumbnail_job)
    monkeypatch.setattr(thumbnail_jobs, "queue_thumbnail_job", fake_queue_thumbnail_job)

    schedule_direct_upload_thumbnails(direct_upload.id, app, user_context={})

    assert called["create"] == 0
    assert called["queue"] == 0
