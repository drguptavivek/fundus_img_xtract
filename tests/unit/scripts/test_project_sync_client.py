import csv
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "project_sync_client", Path(__file__).resolve().parents[3] / "scripts" / "project_sync_client.py"
)
client_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(client_mod)


class FakeClient:
    server = "https://example.test"

    def __init__(self):
        self.min_interval = 0
        self.downloads = []
        self.sidecar_requests = []
        self.fingerprint = "fp1"
        self.capture_date = "2026-09-14"

    def get_json(self, path, **params):
        if path == "/whoami":
            return {
                "project": {"id": 1, "code": "P1"}, "user": {"id": 5, "username": "pi"},
                "expires_at": "2026-12-01T00:00:00+00:00",
                "lab_units": [{"id": 3, "name": "Lab", "pii": False}],
                "page_limits": {"encounters": 200, "direct_images": 500},
                "client_policy": {"max_concurrency": 1, "min_interval_ms": 0},
            }
        if path == "/encounters":
            return {"items": [{
                "uuid": "enc-1", "id": 1, "lab_unit_id": 3, "capture_date": self.capture_date,
                "disease": "DR", "patient_id": None, "patient_name": None,
                "sidecar_fingerprint": "efp",
                "images": [{"uuid": "img-1", "kind": "encounter_set_image", "ext": "jpg", "has_edited": True,
                            "position": 1, "is_pii": False, "source_md5": None,
                            "sidecar_fingerprint": self.fingerprint}],
            }], "next_after_id": None}
        if path == "/direct-images":
            return {"items": [{"uuid": "dir-1", "kind": "direct_image_upload", "ext": "png", "has_edited": False,
                               "created_at": "2026-08-01T00:00:00+00:00", "sidecar_fingerprint": "dfp"}],
                    "next_after_id": None}
        if path == "/exports/latest":
            return {"export": {"job_token": "job1", "status": "done", "files": ["project_encounterset_export.xlsx"]}}
        raise AssertionError(path)

    def post_json(self, path, body):
        if path == "/exports":
            return {"export": {"status": "queued"}}
        self.sidecar_requests.append(body)
        result = {"encounters": {}, "images": {}, "missing": []}
        for uuid in body.get("encounters", []):
            result["encounters"][uuid] = [
                {"record_type": "encounter", "uuid": uuid},
                {"record_type": "task", "task_uuid": "t1", "consensus": {"final_grade": "No DR"}},
                {"record_type": "grade", "task_uuid": "t1", "image_uuid": "img-1", "grade_id": 1,
                 "role_slot": "resident", "grade_name": "No DR", "grader_user_id": 7,
                 "grader_username": "g1", "created_at": "2026-09-15T00:00:00"},
                {"record_type": "grade", "task_uuid": "t1", "image_uuid": "img-1", "grade_id": 2,
                 "role_slot": "resident2", "grade_name": "Mild", "grader_user_id": 8,
                 "grader_username": "g2", "created_at": "2026-09-16T00:00:00"},
            ]
        for uuid in body.get("images", []):
            result["images"][uuid] = [
                {"record_type": "image", "uuid": uuid},
                {"record_type": "grade", "task_uuid": "t1", "grade_id": 1,
                 "annotation_set": {"instances": [{"uuid": "a"}]}},
                {"record_type": "coco", "annotations": [{"source_grade_id": 1}], "categories": []},
            ]
        return result

    def download(self, uuid, variant, target):
        self.downloads.append((uuid, variant))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"img")
        return 3, "x"

    def download_export(self, token, name, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"xlsx")


def _run(tmp_path, fake):
    paths = client_mod.Paths(tmp_path)
    return client_mod.SyncRun(paths, fake, workers=4, include_edited=True, export_wait=0).run()


def test_first_run_builds_layout_sidecars_and_csvs(tmp_path):
    fake = FakeClient()
    result = _run(tmp_path, fake)
    folder = tmp_path / "data/encounters/2026-09/2026-09-14_enc-1"
    assert (folder / "img-1.jpg").is_file()
    assert (folder / "img-1.edited.jpg").is_file()
    assert (folder / "img-1.jsonl").is_file()
    assert (folder / "encounter.jsonl").is_file()
    assert (tmp_path / "data/direct_images/2026-08/dir-1.png").is_file()
    export_dir = Path(result["export_dir"])
    assert (export_dir / "project_encounterset_export.xlsx").is_file()
    with (export_dir / "gradings.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert {r["grader_user_id"] for r in rows} == {"7", "8"}
    assert all(r["graded_at"] for r in rows)
    assert rows[0]["consensus_grade"] == "No DR"
    assert rows[0]["annotation_instances"] == "1"
    with (export_dir / "images.csv").open() as handle:
        assert {r["image_uuid"] for r in csv.DictReader(handle)} == {"img-1", "dir-1"}
    assert json.loads((export_dir / "report.json").read_text())["stats"]["failed"] == 0


def test_second_run_downloads_only_changes(tmp_path):
    fake = FakeClient()
    _run(tmp_path, fake)
    fake.downloads.clear()
    fake.sidecar_requests.clear()
    _run(tmp_path, fake)
    assert fake.downloads == []
    assert fake.sidecar_requests == []

    fake.fingerprint = "fp2"
    _run(tmp_path, fake)
    assert fake.downloads == []
    assert fake.sidecar_requests == [{"images": ["img-1"]}]


def test_moved_capture_date_relocates_without_redownload(tmp_path):
    fake = FakeClient()
    _run(tmp_path, fake)
    fake.downloads.clear()
    fake.capture_date = "2026-10-02"
    _run(tmp_path, fake)
    assert (tmp_path / "data/encounters/2026-10/2026-10-02_enc-1/img-1.jpg").is_file()
    assert fake.downloads == []


def test_refuses_plain_http_for_remote_hosts():
    with pytest.raises(SystemExit):
        client_mod.check_server_url("http://example.org", allow_http=False)
    assert client_mod.check_server_url("http://localhost:5001", allow_http=False) == "http://localhost:5001"
