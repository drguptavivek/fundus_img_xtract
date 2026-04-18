from io import BytesIO
import json

from models import Camera


def _unwrap_view(view_func):
    current = view_func
    while hasattr(current, "__wrapped__"):
        current = current.__wrapped__
    return current


def test_create_camera_with_zip_upload_flag(client, login_user, db_session):
    login_user("test_admin", "Test@2026")

    response = client.post(
        "/admin/camera",
        data={
            "name": "Remedio Pristine",
            "is_zip_upload_enabled": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    camera = db_session.query(Camera).filter_by(name="Remedio Pristine").one()
    assert camera.is_zip_upload_enabled is True


def test_edit_camera_updates_zip_upload_flag(client, login_user, db_session):
    login_user("test_admin", "Test@2026")

    camera = Camera(name="Test Camera", is_zip_upload_enabled=False)
    db_session.add(camera)
    db_session.flush()

    response = client.post(
        f"/admin/camera/{camera.id}/edit",
        data={
            "name": "Test Camera",
            "is_zip_upload_enabled": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    db_session.refresh(camera)
    assert camera.is_zip_upload_enabled is True


def test_zip_upload_form_lists_only_zip_enabled_cameras(client, login_user, db_session, monkeypatch):
    login_user("test_admin", "Test@2026")

    zip_camera = Camera(name="ZIP Camera", is_zip_upload_enabled=True)
    blocked_camera = Camera(name="Blocked Camera", is_zip_upload_enabled=False)
    db_session.add_all([zip_camera, blocked_camera])
    db_session.flush()

    monkeypatch.setattr("remedio_zip_uploads.routes.get_user_lab_unit_ids_no_admin_override", lambda user_id: [100])
    client.application.view_functions["remedio_zip_uploads.upload_form"] = _unwrap_view(
        client.application.view_functions["remedio_zip_uploads.upload_form"]
    )
    response = client.get(
        "/remedio_zip_uploads/upload_files",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )

    assert response.status_code == 200
    assert b"ZIP Camera" in response.data
    assert b"Blocked Camera" not in response.data


def test_zip_upload_rejects_non_zip_enabled_camera(client, login_user, db_session, monkeypatch, tmp_path):
    login_user("test_admin", "Test@2026")

    camera = Camera(name="Blocked Camera", is_zip_upload_enabled=False)
    db_session.add(camera)
    db_session.flush()

    upload_root = tmp_path / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("remedio_zip_uploads.routes.get_daily_upload_dir", lambda: upload_root)
    monkeypatch.setattr("remedio_zip_uploads.routes.db_create_job", lambda *args, **kwargs: "job-token")
    monkeypatch.setattr("remedio_zip_uploads.routes.queue_job", lambda *args, **kwargs: None)
    monkeypatch.setattr("remedio_zip_uploads.routes.get_user_lab_unit_ids_no_admin_override", lambda user_id: [100])
    client.application.view_functions["remedio_zip_uploads.upload_files"] = _unwrap_view(
        client.application.view_functions["remedio_zip_uploads.upload_files"]
    )

    response = client.post(
        "/remedio_zip_uploads/upload",
        data={
            "hospital_id": "100",
            "lab_unit_id": "100",
            "camera_id": str(camera.id),
            "files": (BytesIO(b"PK\x03\x04fakezip"), "case.zip"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"ZIP-enabled camera" in response.data


def test_zip_upload_persists_camera_id_in_sidecar_metadata(client, login_user, db_session, monkeypatch, tmp_path):
    login_user("test_admin", "Test@2026")

    camera = Camera(name="ZIP Camera", is_zip_upload_enabled=True)
    db_session.add(camera)
    db_session.flush()

    daily_upload_dir = tmp_path / "files" / "uploads" / "2026_04_18"
    daily_upload_dir.mkdir(parents=True, exist_ok=True)

    captured = {}

    def fake_create_job(*args, **kwargs):
        captured["create_job"] = True
        return "job-token"

    def fake_queue_job(*args, **kwargs):
        captured["queue_job"] = True

    monkeypatch.setattr("remedio_zip_uploads.routes.get_daily_upload_dir", lambda: daily_upload_dir)
    monkeypatch.setattr("remedio_zip_uploads.routes.db_create_job", fake_create_job)
    monkeypatch.setattr("remedio_zip_uploads.routes.queue_job", fake_queue_job)
    monkeypatch.setattr("remedio_zip_uploads.routes.get_user_lab_unit_ids_no_admin_override", lambda user_id: [100])
    client.application.view_functions["remedio_zip_uploads.upload_files"] = _unwrap_view(
        client.application.view_functions["remedio_zip_uploads.upload_files"]
    )

    response = client.post(
        "/remedio_zip_uploads/upload",
        data={
            "hospital_id": "100",
            "lab_unit_id": "100",
            "camera_id": str(camera.id),
            "files": (BytesIO(b"PK\x03\x04fakezip"), "case.zip"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert captured["create_job"] is True
    assert captured["queue_job"] is True

    meta_path = tmp_path / "files" / "upload_meta" / "case.zip.json"
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["camera_id"] == camera.id
