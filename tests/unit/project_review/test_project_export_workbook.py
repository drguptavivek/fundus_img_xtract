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


def test_project_workbook_adds_wai_sheets_only_when_tables_supplied(tmp_path):
    encounter = SimpleNamespace(
        id=1, uuid="enc-uuid", patient_id="P", capture_date_dt=date(2026, 9, 1),
        capture_date="2026-09-01", lab_unit_id=7, encounter_verified_status="verified",
        metadata_json={},
    )
    image = SimpleNamespace(
        id=2, uuid="img-uuid", patient_encounter_id=1, original_filename="x.jpg",
        edited_filename=None, spatial_position=1, visible_to_grader=True,
        is_reviewed=False, is_not_gradable=False,
    )
    ai = {
        "ai_runs": [
            {"run_scope": "encounter", "run_id": "run-1", "encounter_uuid": "enc-uuid", "task_uuid": None,
             "image_uuid": None, "ai_model": "Madhunetra", "ai_model_version": "1", "source": "automatic",
             "status": "success", "request_id": "q", "prediction_id": None, "report_id": "r1", "http_status": 200,
             "error_code": None, "error_message": None, "retry_count": None, "created_at": None,
             "started_at": None, "finished_at": None, "request_manifest": "{}", "response": "{}",
             "config_snapshot": "{}"},
            {"run_scope": "task", "run_id": "9", "encounter_uuid": "enc-uuid", "task_uuid": "t",
             "image_uuid": "img-uuid", "ai_model": "Glaucoma", "ai_model_version": "2", "status": "failed",
             "error_code": "boom"},
        ],
        "ai_image_results": [
            {"run_id": "run-1", "encounter_uuid": "enc-uuid", "image_uuid": "img-uuid", "remote_key": "k",
             "submitted_eye": "left", "detected_eye": "left", "laterality_mismatch": False, "is_primary": True,
             "similarity_score": 0.8, "upload_attempts": 1, "quality_state": "gradable", "raw_output": "{}"},
        ],
        "ai_target_results": [
            {"run_id": "run-1", "encounter_uuid": "enc-uuid", "image_uuid": "img-uuid", "target_key": "dr",
             "raw_label": "Mild", "raw_score": 0.9, "mapped_grade": "Mild NPDR", "derivation_reason": "provider",
             "grade_id": 1},
            {"run_id": "run-1", "encounter_uuid": "enc-uuid", "image_uuid": "img-uuid", "target_key": "dme",
             "raw_label": "No", "raw_score": 0.1, "mapped_grade": "No DME", "derivation_reason": "provider",
             "grade_id": 2},
        ],
    }
    ai_grades = [{
        "grade_id": 7, "task_uuid": "t", "encounter_uuid": "enc-uuid", "image_uuid": "img-uuid",
        "disease": "Glaucoma", "grade_name": "Suspect", "ai_model": "Glaucoma", "ai_model_version": "2",
        "ai_probability": 0.83, "ai_predicted_class_name": "GON", "ai_review_status": "ok",
    }]
    plain = tmp_path / "plain.xlsx"
    _write_workbook(plain, [encounter], [image], [])
    assert "WAI Encounter Results" not in pd.read_excel(plain, sheet_name=None)

    path = tmp_path / "wai.xlsx"
    _write_workbook(path, [encounter], [image], [], wai_tables=export_service._wai_sheet_rows(ai, ai_grades))
    sheets = pd.read_excel(path, sheet_name=None)
    enc = sheets["WAI Encounter Results"]
    assert list(enc["run_id"]) == ["run-1"]
    assert enc.iloc[0]["dr_positive"] and not enc.iloc[0]["dme_positive"]
    assert enc.iloc[0]["submitted_image_count"] == 1
    assert not {"request_manifest", "response", "remote_key"} & set(enc.columns)
    img = sheets["WAI Image Results"]
    assert list(img["target_key"].iloc[:2]) == ["dr", "dme"]
    assert img.iloc[0]["mapped_grade"] == "Mild NPDR" and "raw_output" not in img.columns
    glaucoma = img.iloc[2]
    assert glaucoma["ai_model"] == "Glaucoma" and glaucoma["run_status"] == "failed"
    assert glaucoma["mapped_grade"] == "Suspect" and glaucoma["raw_score"] == 0.83 and glaucoma["raw_label"] == "GON"
