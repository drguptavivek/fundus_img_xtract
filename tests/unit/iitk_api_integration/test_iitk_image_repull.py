import json
import random
from contextlib import contextmanager
from datetime import date
from io import BytesIO

from PIL import Image

from iitk_api_integration import image_repull
from iitk_api_integration.models import IITKApiSessionLink
from models import EncounterSetImage, PatientEncounters
from tests.unit.iitk_api_integration.test_iitk_api_service import setup_config
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


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.fetched = []

    def get_image(self, session_id, filename):
        self.fetched.append((session_id, filename))
        return self.content


def _candidate(path, *, filename="primary.jpg", size=None):
    return image_repull.Candidate(1, 10, 1, "sess", 1, filename, size, path)


def test_damaged_file_is_replaced_losslessly_and_logged(tmp_path, monkeypatch):
    log = tmp_path / "repull.jsonl"
    monkeypatch.setattr(image_repull, "RESTORE_LOG", log)
    path = tmp_path / "a.jpg"
    path.write_bytes(_photo(75))
    original = _photo(95, with_exif=True)
    summary = image_repull.RepullSummary()
    client = FakeClient(original)
    image_repull._repair_one(client, _candidate(path, size=len(original)), {}, summary)

    assert summary.replaced == 1 and summary.failed == 0
    assert client.fetched == [("sess", "primary.jpg")]
    restored = path.read_bytes()
    assert b"Patient Jane" not in restored and not has_default_quality_75_tables(restored[:4096])
    with Image.open(BytesIO(original)) as before, Image.open(BytesIO(restored)) as after:
        assert list(after.getdata()) == list(before.getdata())
    assert not list(tmp_path.glob(".*.repull"))
    (line,) = log.read_text().splitlines()
    assert json.loads(line)["bytes_after"] == len(restored)


def test_changed_source_and_quality_75_source_are_left_alone(tmp_path):
    path = tmp_path / "a.jpg"
    original = _photo(75)
    path.write_bytes(original)
    summary = image_repull.RepullSummary()
    image_repull._repair_one(FakeClient(_photo(95)), _candidate(path, size=1), {}, summary)
    image_repull._repair_one(FakeClient(_photo(75)), _candidate(path), {}, summary)
    assert summary.source_changed == 1 and summary.source_is_quality_75 == 1 and summary.replaced == 0
    assert path.read_bytes() == original


def test_missing_filename_falls_back_to_the_provider_inventory(tmp_path):
    class InventoryClient(FakeClient):
        def list_images(self, session_id):
            image = type("I", (), {"position": "primary", "filename": "from-inventory.jpg"})
            return type("Inv", (), {"images": (image,)})

    path = tmp_path / "a.jpg"
    path.write_bytes(_photo(75))
    client = InventoryClient(_photo(95))
    summary = image_repull.RepullSummary()
    image_repull._repair_one(client, _candidate(path, filename=None), {}, summary)
    assert summary.replaced == 1 and client.fetched == [("sess", "from-inventory.jpg")]


def test_candidates_are_damaged_iitk_files_newest_first(db_session, core_test_data, tmp_path, monkeypatch):
    runtime = setup_config(db_session, core_test_data)
    project_id, config_id = runtime.project_id, runtime.id
    monkeypatch.setattr(image_repull, "BASE_DIR", tmp_path)
    (tmp_path / "f").mkdir()
    for index, (day, quality) in enumerate([(date(2026, 9, 1), 75), (date(2026, 9, 3), 75), (date(2026, 9, 2), 95)]):
        encounter = PatientEncounters(
            name="n", patient_id=f"P{index}", capture_date=day.isoformat(), capture_date_dt=day,
            lab_unit_id=core_test_data["lab_a1"].id, project_id=project_id, disease_id=core_test_data["dr"].id,
            is_set_based=True,
        )
        db_session.add(encounter)
        db_session.flush()
        name = f"img{index}.jpg"
        (tmp_path / "f" / name).write_bytes(_photo(quality))
        db_session.add(EncounterSetImage(
            patient_encounter_id=encounter.id, spatial_position=1, original_filename=name, folder_rel="f",
            project_id=project_id, metadata_json={"source_filename": "primary.jpg"},
        ))
        db_session.add(IITKApiSessionLink(
            config_id=config_id, source_session_id=f"S{index}", patient_encounter_id=encounter.id,
            source_status="complete", source_image_count=1, local_image_count=1,
        ))
    db_session.flush()

    @contextmanager
    def same_session():
        yield db_session

    monkeypatch.setattr(image_repull, "get_db_session", same_session)
    groups = image_repull._damaged_encounters(limit_images=10, before=None, summary=image_repull.RepullSummary())
    assert [key[1] for key in groups] == [date(2026, 9, 3), date(2026, 9, 1)]
    one = image_repull._damaged_encounters(limit_images=1, before=None, summary=image_repull.RepullSummary())
    assert [key[1] for key in one] == [date(2026, 9, 3)]
    older = image_repull._damaged_encounters(limit_images=10, before=date(2026, 9, 3), summary=image_repull.RepullSummary())
    assert [key[1] for key in older] == [date(2026, 9, 1)]
