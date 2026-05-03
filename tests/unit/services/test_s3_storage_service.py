from __future__ import annotations

from services.s3 import get_storage_backend_info_for_hospital, upload_local_path_to_hospital_s3


def test_s3_upload_service_returns_none_when_hospital_has_no_active_config(monkeypatch, tmp_path):
    monkeypatch.setattr("services.s3.storage.get_active_s3_config", lambda hospital_id: None)

    local_path = tmp_path / "files" / "direct_uploads" / "image.png"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"image-bytes")

    assert upload_local_path_to_hospital_s3(hospital_id=1, file_content=b"image-bytes", local_path=local_path) is None


def test_s3_storage_backend_info_delegates_to_shared_utility(monkeypatch):
    monkeypatch.setattr("services.s3.storage.get_storage_backend_info", lambda hospital_id: {"backend": "local", "hospital_id": hospital_id})

    assert get_storage_backend_info_for_hospital(3) == {"backend": "local", "hospital_id": 3}
