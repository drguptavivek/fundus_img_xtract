from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
from PIL import Image
from zipfile import ZipFile

from project_review import export_service
from project_review.export_service import _write_image_bundle, _write_workbook, validate_export_request


def test_project_workbook_has_join_keys_partial_grades_and_no_source_filename(tmp_path):
    encounter = SimpleNamespace(
        id=1, uuid="encounter-uuid", patient_id="MRN-CORE-100",
        capture_date_dt=date(2026, 9, 1),
        capture_date="2026-09-01", lab_unit_id=7, encounter_verified_status="verified",
        metadata_json={
            "patient": {
                "patient_age_yrs": 63,
                "sex": "female",
                "hospital_UHID": "HOSPITAL-100",
                "mrn": "MRN-100",
                "remidio_patient_raw_metadata": {"name": "SECRET PERSON"},
            },
            "encounter": {
                "mode_capture": "clinic",
                "clinical_note": "=FORMULA()",
                "remidio_encounter_raw_metadata": {"patientId": "SECRET-MRN-100"},
            },
            "upload": {"source_filename": "SECRET-MRN-100.zip"},
        },
    )
    image = SimpleNamespace(
        id=2, uuid="image-uuid", patient_encounter_id=1,
        original_filename="SECRET-MRN-100.jpg", edited_filename=None,
        spatial_position=1, visible_to_grader=True, is_reviewed=True,
        is_not_gradable=False,
    )
    label = SimpleNamespace(impression="Positive")
    grade = SimpleNamespace(
        id=4, role_slot="resident", grade_name="Positive", label=label,
        selected_features_json='[{"label":"lesion"}]',
        feature_geometry_json={"items": [{"geometry_type": "box"}]},
        updated_at=datetime(2026, 9, 2, tzinfo=timezone.utc), time_taken=12.5,
    )
    task = SimpleNamespace(
        id=3, uuid="task-uuid", patient_encounter_id=None,
        encounter_set_image=image, grading_target_level="image",
        disease=SimpleNamespace(name="OSN"), state="resident_done",
        encounter_set_package=None, encounter_set_scope_id=None,
        grades=[grade], consensus=None,
    )
    path = tmp_path / "project.xlsx"
    _write_workbook(path, [encounter], [image], [task])

    sheets = pd.read_excel(path, sheet_name=None)
    assert set(sheets) == {"Encounters", "Images", "Tasks", "Grade Submissions", "Final Grades"}
    assert sheets["Images"].iloc[0]["exported_filename"] == "image-uuid.jpg"
    assert sheets["Tasks"].iloc[0]["task_uuid"] == "task-uuid"
    assert sheets["Grade Submissions"].iloc[0]["role_slot"] == "resident"
    encounter_row = sheets["Encounters"].iloc[0]
    assert encounter_row["patient_id"] == "MRN-CORE-100"
    assert encounter_row["metadata_patient_patient_age_yrs"] == 63
    assert encounter_row["metadata_patient_sex"] == "female"
    assert encounter_row["metadata_patient_hospital_UHID"] == "HOSPITAL-100"
    assert encounter_row["metadata_patient_mrn"] == "MRN-100"
    assert encounter_row["metadata_encounter_mode_capture"] == "clinic"
    assert encounter_row["metadata_encounter_clinical_note"] == "'=FORMULA()"
    assert not any(column.startswith("metadata_upload_") for column in sheets["Encounters"])
    assert not any("raw_metadata" in column for column in sheets["Encounters"])
    assert not bool(sheets["Final Grades"].iloc[0]["has_persisted_final_grade"])
    assert sheets["Final Grades"].iloc[0]["task_state"] == "resident_done"
    assert "SECRET-MRN" not in path.read_bytes().decode("latin1", errors="ignore")


def test_project_export_rejects_reversed_date_range():
    try:
        validate_export_request(
            project_id=1, actor_user_id=2, kind="workbook",
            date_from=date(2026, 9, 2), date_to=date(2026, 9, 1),
            grading_filter="all",
        )
    except ValueError as exc:
        assert "start date" in str(exc)
    else:
        raise AssertionError("Expected reversed date range to be rejected")


def test_image_bundle_uses_encounter_and_uuid_filename_without_image_count_cap(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "MRN-SECRET.jpg"
    Image.new("RGB", (4, 3)).save(source)
    encounter = SimpleNamespace(id=1, uuid="encounter-uuid")
    image = SimpleNamespace(
        uuid="image-uuid", patient_encounter_id=1, edited_filename=None,
        original_filename=source.name, folder_rel="source", s3_config_id=None,
        s3_object_key=None, s3_object_key_edited=None,
    )
    monkeypatch.setattr(export_service, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        export_service,
        "write_annotation_export",
        lambda _rows, destination: {"schema_version": 1, "tasks": []},
    )
    monkeypatch.setattr(export_service, "write_coco_exports", lambda *_args: [])
    monkeypatch.setattr(export_service, "write_annotator_exports", lambda *_args: None)
    _write_image_bundle(tmp_path, [encounter], [image], [])
    with ZipFile(tmp_path / "1.zip") as archive:
        assert archive.namelist() == [
            "EncounterSets/encounter-uuid/image-uuid.jpg",
        ]
        assert "MRN-SECRET" not in "\n".join(archive.namelist())
