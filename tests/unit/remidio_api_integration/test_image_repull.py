import random
from contextlib import contextmanager
from datetime import date, datetime, timezone
from io import BytesIO

import pytest
from PIL import Image

from models import (
    BASE_DIR, EncounterSetImage, PatientEncounters, Project, RemidioConnection, RemidioExam, RemidioImage,
)
from remidio_api_integration import image_repull
from utils.image_processing import has_default_quality_75_tables


def _photo(quality, *, with_exif=False):
    rng = random.Random(3)
    img = Image.new("RGB", (96, 96))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(96 * 96)])
    out = BytesIO()
    kwargs = {}
    if with_exif:
        exif = img.getexif()
        exif[0x010E] = "Patient Jane"
        kwargs["exif"] = exif
    img.save(out, format="JPEG", quality=quality, **kwargs)
    return out.getvalue()


def test_quality_75_signature_is_detected():
    assert has_default_quality_75_tables(_photo(75)[:4096])
    assert not has_default_quality_75_tables(_photo(95)[:4096])
    assert not has_default_quality_75_tables(b"not a jpeg")


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.downloaded = []

    def download_file(self, url, **_kwargs):
        self.downloaded.append(url)
        return self.content, "image/jpeg"


def test_damaged_file_is_replaced_losslessly_and_without_exif(tmp_path, monkeypatch):
    log = tmp_path / "repull.jsonl"
    monkeypatch.setattr(image_repull, "RESTORE_LOG", log)
    path = tmp_path / "a.jpg"
    path.write_bytes(_photo(75))
    original = _photo(95, with_exif=True)
    summary = image_repull.RepullSummary()
    image_repull._repair_one(FakeClient(original), image_repull.Candidate("img-1", path), "https://signed/1", summary)

    assert summary.replaced == 1 and summary.failed == 0
    restored = path.read_bytes()
    assert b"Patient Jane" not in restored and not has_default_quality_75_tables(restored[:4096])
    with Image.open(BytesIO(original)) as before, Image.open(BytesIO(restored)) as after:
        assert list(after.getdata()) == list(before.getdata())
    assert not list(tmp_path.glob(".*.repull"))  # no temp file left behind
    import json

    (line,) = log.read_text().splitlines()
    record = json.loads(line)
    assert record["remidio_image_id"] == "img-1" and record["bytes_after"] == len(restored)


def test_source_that_is_itself_quality_75_is_left_alone(tmp_path):
    path = tmp_path / "a.jpg"
    path.write_bytes(_photo(75))
    summary = image_repull.RepullSummary()
    image_repull._repair_one(FakeClient(_photo(75)), image_repull.Candidate("img-1", path), "https://signed/1", summary)
    assert summary.source_is_quality_75 == 1 and summary.replaced == 0


def test_image_missing_from_source_is_counted_not_downloaded(tmp_path):
    summary = image_repull.RepullSummary()
    client = FakeClient(b"")
    image_repull._repair_one(client, image_repull.Candidate("img-1", tmp_path / "a.jpg"), None, summary)
    assert summary.not_returned_by_source == 1 and client.downloaded == []


def test_candidates_are_damaged_files_newest_exam_first_and_database_is_untouched(db_session, core_test_data, tmp_path, monkeypatch):
    project = Project(title="Repull", code="REPULL", active=True)
    db_session.add(project)
    db_session.flush()
    connection = RemidioConnection(
        name="c", base_url="https://x", client_name="n", client_identification_token_encrypted="t",
        email_encrypted="e", password_encrypted="p", secret_salt="s",
    )
    db_session.add(connection)
    db_session.flush()
    monkeypatch.setattr(image_repull, "BASE_DIR", tmp_path)
    rows = []
    for index, (exam_day, quality) in enumerate([(date(2026, 9, 1), 75), (date(2026, 9, 3), 75), (date(2026, 9, 2), 95)]):
        encounter = PatientEncounters(
            name="n", patient_id=f"P{index}", capture_date=exam_day.isoformat(), capture_date_dt=exam_day,
            lab_unit_id=core_test_data["lab_a1"].id, project_id=project.id, disease_id=core_test_data["dr"].id,
            is_set_based=True,
        )
        db_session.add(encounter)
        db_session.flush()
        name = f"img{index}.jpg"
        (tmp_path / "f").mkdir(exist_ok=True)
        (tmp_path / "f" / name).write_bytes(_photo(quality))
        image = EncounterSetImage(
            patient_encounter_id=encounter.id, spatial_position=1, original_filename=name, folder_rel="f",
            project_id=project.id,
        )
        db_session.add(image)
        db_session.flush()
        exam = RemidioExam(
            remidio_connection_id=connection.id, remidio_exam_id=f"E{index}", site_custom_identifier="SITE",
            pull_source="t", exam_date=datetime(exam_day.year, exam_day.month, exam_day.day, 6, tzinfo=timezone.utc),
        )
        db_session.add(exam)
        db_session.flush()
        db_session.add(RemidioImage(remidio_exam_id=exam.id, encounter_set_image_id=image.id, remidio_image_id=f"I{index}"))
        rows.append(image)
    db_session.flush()

    @contextmanager
    def same_session():
        yield db_session

    monkeypatch.setattr(image_repull, "get_db_session", same_session)
    summary = image_repull.repull_batch(limit_images=10, dry_run=True)
    assert summary.candidates == 2 and summary.already_ok == 1 and summary.groups == 2

    groups = image_repull._damaged_groups(limit_images=10, before=None, summary=image_repull.RepullSummary())
    assert [key[2] for key in groups] == [date(2026, 9, 3), date(2026, 9, 1)]  # newest first, the intact 09-02 skipped
    one_per_batch = image_repull._damaged_groups(limit_images=1, before=None, summary=image_repull.RepullSummary())
    assert [key[2] for key in one_per_batch] == [date(2026, 9, 3)]  # stops at the day boundary
    older = image_repull._damaged_groups(limit_images=10, before=date(2026, 9, 3), summary=image_repull.RepullSummary())
    assert [key[2] for key in older] == [date(2026, 9, 1)]


def test_a_pause_separates_encounters(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(image_repull.time, "sleep", sleeps.append)
    monkeypatch.setattr(image_repull, "PAUSE_BETWEEN_ENCOUNTERS_SECONDS", 10.0)
    monkeypatch.setattr(image_repull, "PAUSE_BETWEEN_API_CALLS_SECONDS", 2.5)
    monkeypatch.setattr(image_repull, "PAUSE_BETWEEN_DOWNLOADS_SECONDS", 1.0)
    candidates = [image_repull.Candidate(f"i{n}", tmp_path / f"{n}.jpg", encounter) for n, encounter in enumerate([7, 7, 9])]
    for candidate in candidates:
        candidate.path.write_bytes(_photo(75))
    groups = {(1, "SITE", date(2026, 9, 1)): candidates}
    monkeypatch.setattr(image_repull, "_damaged_groups", lambda **_k: groups)
    monkeypatch.setattr(image_repull, "_fresh_image_urls", lambda clients, *_a: clients.setdefault(1, FakeClient(_photo(95))) and {})

    summary = image_repull.repull_batch(limit_images=10)
    assert sleeps.count(10.0) == 1  # only between encounter 7 and encounter 9
    assert summary.not_returned_by_source == 3
