from pathlib import Path

from review.discrepancy_export import ExportTaskRow, _build_task_payload


def _row_base(**overrides):
    data = dict(
        task_id=1,
        task_uuid="task-uuid",
        disease="DR",
        lab_unit="Lab A",
        hospital="Hosp A",
        state="completed",
        consensus_status=None,
        consensus_method=None,
        final_impression=None,
        grading_details_json="[]",
        ai_review_comments=[],
        ai_review_statuses=[],
        encounter_file_id=None,
        encounter_file_uuid=None,
        encounter_filename=None,
        encounter_upload_date=None,
        direct_image_upload_id=None,
        direct_image_uuid=None,
        direct_filename=None,
        direct_folder_rel=None,
    )
    data.update(overrides)
    return ExportTaskRow(**data)


def test_build_payload_adds_original_filename_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "review.discrepancy_export._load_ai_model_meta",
        lambda task_ids: {},
    )
    monkeypatch.setattr(
        "review.discrepancy_export._load_encounter_paths",
        lambda ids: {1: (Path("/tmp/enc.jpg"), ".jpg")},
    )
    monkeypatch.setattr(
        "review.discrepancy_export._load_direct_paths",
        lambda ids: {2: (Path("/tmp/direct.jpg"), ".jpg")},
    )

    rows = [
        _row_base(encounter_file_id=1, encounter_file_uuid="enc-uuid", encounter_filename="enc.jpg"),
        _row_base(
            task_id=2,
            task_uuid="task-uuid-2",
            direct_image_upload_id=2,
            direct_image_uuid="dir-uuid",
            direct_filename="direct.jpg",
        ),
    ]

    payload = _build_task_payload(rows, include_original_filenames=True)

    assert payload[0]["original_upload_filename"] == "enc.jpg"
    assert payload[1]["original_upload_filename"] == "direct.jpg"


def test_build_payload_skips_original_filename_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "review.discrepancy_export._load_ai_model_meta",
        lambda task_ids: {},
    )
    monkeypatch.setattr(
        "review.discrepancy_export._load_encounter_paths",
        lambda ids: {1: (Path("/tmp/enc.jpg"), ".jpg")},
    )

    rows = [
        _row_base(encounter_file_id=1, encounter_file_uuid="enc-uuid", encounter_filename="enc.jpg"),
    ]

    payload = _build_task_payload(rows)

    assert "original_upload_filename" not in payload[0]
