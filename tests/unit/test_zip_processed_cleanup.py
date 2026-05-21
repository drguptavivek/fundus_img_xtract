from __future__ import annotations

from uuid import uuid4

from models import EncounterFile, Job, JobItem, PatientEncounters, ZipFile
from zip_processor import cleanup_processed_zip_intake_files


def _configure_zip_dirs(monkeypatch, tmp_path):
    upload_dir = tmp_path / "zip_upload_zips"
    processed_dir = tmp_path / "zips_upload_processed"
    monkeypatch.setattr("zip_processor.UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("zip_processor.PROCESSED_DIR", processed_dir)
    return upload_dir, processed_dir


def _create_intake_zip(upload_dir, date_folder: str, filename: str):
    path = upload_dir / date_folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"zip-bytes")
    return path


def _create_ingested_zip(db_session, filename: str, *, with_extracted_file: bool = True):
    zip_file = ZipFile(
        zip_filename=filename,
        md5_hash=uuid4().hex,
    )
    db_session.add(zip_file)
    db_session.flush()

    encounter = PatientEncounters(
        zip_file_id=zip_file.id,
        name="Cleanup Test",
        patient_id=f"P{uuid4().hex[:8]}",
        capture_date="2026-04-20",
    )
    db_session.add(encounter)
    db_session.flush()

    if with_extracted_file:
        db_session.add(
            EncounterFile(
                patient_encounter_id=encounter.id,
                filename=f"{uuid4().hex}.jpg",
                file_type="image",
            )
        )
        db_session.flush()

    return zip_file


def test_cleanup_processed_zip_intake_files_dry_run_only_reports_eligible(
    db_session,
    monkeypatch,
    tmp_path,
):
    upload_dir, _processed_dir = _configure_zip_dirs(monkeypatch, tmp_path)
    filename = f"cleanup_{uuid4().hex}.zip"
    source = _create_intake_zip(upload_dir, "2026_04_20", filename)
    _create_ingested_zip(db_session, filename)

    result = cleanup_processed_zip_intake_files(
        db_session,
        date_folder="2026_04_20",
        dry_run=True,
    )

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["moved"] == 0
    assert result["items"][0]["status"] == "eligible"
    assert source.exists()


def test_cleanup_processed_zip_intake_files_moves_only_confirmed_ingested_zip(
    db_session,
    monkeypatch,
    tmp_path,
):
    upload_dir, processed_dir = _configure_zip_dirs(monkeypatch, tmp_path)
    filename = f"cleanup_{uuid4().hex}.zip"
    source = _create_intake_zip(upload_dir, "2026_04_20", filename)
    _create_ingested_zip(db_session, filename)

    result = cleanup_processed_zip_intake_files(
        db_session,
        date_folder="2026_04_20",
        dry_run=False,
    )

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["moved"] == 1
    assert not source.exists()
    assert (processed_dir / "2026_04_20" / filename).exists()


def test_cleanup_processed_zip_intake_files_skips_without_extracted_file(
    db_session,
    monkeypatch,
    tmp_path,
):
    upload_dir, _processed_dir = _configure_zip_dirs(monkeypatch, tmp_path)
    filename = f"cleanup_{uuid4().hex}.zip"
    source = _create_intake_zip(upload_dir, "2026_04_20", filename)
    _create_ingested_zip(db_session, filename, with_extracted_file=False)

    result = cleanup_processed_zip_intake_files(
        db_session,
        date_folder="2026_04_20",
        dry_run=False,
    )

    assert result["eligible"] == 0
    assert result["moved"] == 0
    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "missing_extracted_encounter_file"
    assert source.exists()


def test_cleanup_processed_zip_intake_files_skips_active_zip_job_item(
    db_session,
    monkeypatch,
    tmp_path,
):
    upload_dir, _processed_dir = _configure_zip_dirs(monkeypatch, tmp_path)
    filename = f"cleanup_{uuid4().hex}.zip"
    source = _create_intake_zip(upload_dir, "2026_04_20", filename)
    _create_ingested_zip(db_session, filename)
    job = Job(token=f"cleanup-{uuid4().hex}", status="processing", upload_type="zip")
    db_session.add(job)
    db_session.flush()
    db_session.add(JobItem(job_id=job.id, filename=filename, state="processing"))
    db_session.flush()

    result = cleanup_processed_zip_intake_files(
        db_session,
        date_folder="2026_04_20",
        dry_run=False,
    )

    assert result["eligible"] == 0
    assert result["moved"] == 0
    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "active_job_item_exists"
    assert source.exists()
