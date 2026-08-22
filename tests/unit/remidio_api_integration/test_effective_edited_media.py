from types import SimpleNamespace

from remidio_api_integration import service


def test_no_pii_export_prefers_edited_encounter_set_image(tmp_path, monkeypatch):
    folder = tmp_path / "files" / "encounter_sets" / "1"
    folder.mkdir(parents=True)
    (folder / "original.jpg").write_bytes(b"original-with-pii")
    (folder / "edited.jpg").write_bytes(b"edited-without-pii")
    image = SimpleNamespace(
        id=1,
        folder_rel="files/encounter_sets/1",
        original_filename="original.jpg",
        edited_filename="edited.jpg",
        s3_config_id=None,
        s3_object_key=None,
        s3_object_key_edited=None,
    )
    monkeypatch.setattr(service, "BASE_DIR", tmp_path)

    extension, payload = service._encounter_set_export_image_bytes(None, image)

    assert extension == ".jpg"
    assert payload == b"edited-without-pii"
