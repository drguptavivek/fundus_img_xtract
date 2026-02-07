from datetime import datetime, timezone

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
        image_uuid=None,
        encounter_file_id=None,
        encounter_file_uuid=None,
        encounter_filename=None,
        encounter_upload_date=None,
        direct_image_upload_id=None,
        direct_image_uuid=None,
        direct_filename=None,
        direct_edited_filename=None,
        direct_folder_rel=None,
    )
    data.update(overrides)
    return ExportTaskRow(**data)


def test_build_payload_adds_original_filename_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "review.discrepancy_export._load_ai_model_meta",
        lambda task_ids: {},
    )

    rows = [
        _row_base(
            encounter_file_id=1,
            encounter_file_uuid="enc-uuid",
            encounter_filename="enc.jpg",
            encounter_upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        _row_base(
            task_id=2,
            task_uuid="task-uuid-2",
            direct_image_upload_id=2,
            direct_image_uuid="dir-uuid",
            direct_filename="direct.jpg",
            direct_folder_rel="files/direct_uploads/2024_01_01_user1",
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

    rows = [
        _row_base(
            encounter_file_id=1,
            encounter_file_uuid="enc-uuid",
            encounter_filename="enc.jpg",
            encounter_upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
    ]

    payload = _build_task_payload(rows)

    assert "original_upload_filename" not in payload[0]
