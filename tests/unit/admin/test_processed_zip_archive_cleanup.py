from __future__ import annotations

import importlib
from uuid import uuid4
from pathlib import Path

from admin.disk_usage import cleanup_processed_zip_archives
from models import EncounterFile, Job, JobItem, PatientEncounters, ZipFile

disk_usage_admin = importlib.import_module("admin.disk_usage")


def _create_processed_zip(processed_dir, date_folder: str, filename: str):
    path = processed_dir / date_folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"processed-zip")
    return path


def _create_ingested_zip(db_session, filename: str, *, with_extracted_file: bool = True):
    zip_file = ZipFile(zip_filename=filename, md5_hash=uuid4().hex)
    db_session.add(zip_file)
    db_session.flush()

    encounter = PatientEncounters(
        zip_file_id=zip_file.id,
        name="Archive Cleanup Test",
        patient_id=f"P{uuid4().hex[:8]}",
        capture_date="2026-02-18",
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


def test_processed_zip_archive_cleanup_dry_run_keeps_confirmed_file(
    app,
    db_session,
    tmp_path,
):
    processed_dir = tmp_path / "zips_upload_processed"
    filename = f"archive_{uuid4().hex}.zip"
    source = _create_processed_zip(processed_dir, "2026_02_18", filename)
    _create_ingested_zip(db_session, filename)

    with app.app_context():
        result = cleanup_processed_zip_archives(
            db_session,
            processed_dir=processed_dir,
            retention_days=30,
            dry_run=True,
        )

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["deleted"] == 0
    assert result["items"][0]["status"] == "eligible"
    assert source.exists()


def test_processed_zip_archive_cleanup_deletes_only_confirmed_file(
    app,
    db_session,
    tmp_path,
):
    processed_dir = tmp_path / "zips_upload_processed"
    filename = f"archive_{uuid4().hex}.zip"
    source = _create_processed_zip(processed_dir, "2026_02_18", filename)
    _create_ingested_zip(db_session, filename)

    with app.app_context():
        result = cleanup_processed_zip_archives(
            db_session,
            processed_dir=processed_dir,
            retention_days=30,
            dry_run=False,
        )

    assert result["eligible"] == 1
    assert result["deleted"] == 1
    assert result["deleted_size_bytes"] > 0
    assert not source.exists()


def test_processed_zip_archive_cleanup_skips_missing_zip_file_row(
    app,
    db_session,
    tmp_path,
):
    processed_dir = tmp_path / "zips_upload_processed"
    filename = f"archive_{uuid4().hex}.zip"
    source = _create_processed_zip(processed_dir, "2026_02_18", filename)

    with app.app_context():
        result = cleanup_processed_zip_archives(
            db_session,
            processed_dir=processed_dir,
            retention_days=30,
            dry_run=False,
        )

    assert result["eligible"] == 0
    assert result["deleted"] == 0
    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "missing_zip_file_row"
    assert source.exists()


def test_processed_zip_archive_cleanup_skips_active_zip_job_item(
    app,
    db_session,
    tmp_path,
):
    processed_dir = tmp_path / "zips_upload_processed"
    filename = f"archive_{uuid4().hex}.zip"
    source = _create_processed_zip(processed_dir, "2026_02_18", filename)
    _create_ingested_zip(db_session, filename)

    job = Job(token=f"archive-{uuid4().hex}", status="processing", upload_type="zip")
    db_session.add(job)
    db_session.flush()
    db_session.add(JobItem(job_id=job.id, filename=filename, state="processing"))
    db_session.flush()

    with app.app_context():
        result = cleanup_processed_zip_archives(
            db_session,
            processed_dir=processed_dir,
            retention_days=30,
            dry_run=False,
        )

    assert result["eligible"] == 0
    assert result["deleted"] == 0
    assert result["skipped"] == 1
    assert result["items"][0]["reason"] == "active_job_item_exists"
    assert source.exists()


def test_delete_old_processed_zips_preview_returns_modal(
    app,
    monkeypatch,
):
    def fake_get_db_session():
        class Context:
            def __enter__(self):
                return object()

            def __exit__(self, exc_type, exc, tb):
                return False

        return Context()

    def fake_cleanup(db_session, *, processed_dir, retention_days, dry_run, limit):
        return {
            "dry_run": dry_run,
            "retention_days": retention_days,
            "scanned": 2,
            "eligible": 1,
            "eligible_size_bytes": 1234,
            "deleted": 0,
            "deleted_size_bytes": 0,
            "skipped": 1,
            "errors": 0,
            "items": [
                {
                    "filename": "case.zip",
                    "status": "eligible",
                    "reason": "eligible",
                    "size_bytes": 1234,
                }
            ],
        }

    processed_dir = Path(app.root_path) / "files" / "zips_upload_processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(disk_usage_admin, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(disk_usage_admin, "cleanup_processed_zip_archives", fake_cleanup)

    with app.test_request_context(
        "/admin/disk-usage/delete-old-zips",
        method="POST",
        data={"retention_days": "30", "dry_run": "true", "response": "modal"},
    ):
        response = disk_usage_admin.delete_old_processed_zips.__wrapped__()

    assert "processedZipCleanupModal" in response
    assert "Delete ZIPs" in response
