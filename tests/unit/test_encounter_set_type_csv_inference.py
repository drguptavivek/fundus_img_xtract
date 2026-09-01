from __future__ import annotations

import io
from pathlib import Path

import pytest

from encounter_set_types.csv_inference import CsvInferenceError, infer_csv_configuration


def _infer(text: str):
    return infer_csv_configuration(io.BytesIO(text.encode("utf-8")), "source.csv").payload


def test_inference_collapses_supported_eye_suffix_conventions():
    for right, left in (("od", "os"), ("rt", "lt"), ("re", "le")):
        payload = _infer(
            f"instance_id,submission_date,co_density_{right},co_density_{left},photo_{right},photo_{left}\n"
            "P1,2026-01-01T10:00:00Z,Nebular,Leucoma,right.jpg,left.jpg\n"
        )

        fields = {field["key"]: field for field in payload["metadata_schema_json"]["fields"]}
        assert fields["co_density"]["scope"] == "image"
        mappings = payload["mapper_draft"]["column_mappings"]
        assert {
            (mapping["source_column"], mapping.get("laterality"))
            for mapping in mappings
            if mapping["canonical_key"] == "co_density"
        } == {(f"co_density_{right}", "OD"), (f"co_density_{left}", "OS")}
        reserved = payload["mapper_draft"]["reserved_columns"]
        image_references = {
            (item["source_column"], item.get("laterality"))
            for item in reserved
            if item["role"] == "clinical_image_filename"
        }
        assert image_references == {
            (f"photo_{right}", "OD"),
            (f"photo_{left}", "OS"),
        }


def test_inference_rejects_mixed_eye_suffix_conventions_for_same_field():
    with pytest.raises(CsvInferenceError, match="mixes suffix conventions"):
        _infer("instance_id,co_present_od,co_present_lt\nP1,Present,Absent\n")


def test_inference_maps_known_standards_and_excludes_empty_columns():
    payload = _infer(
        "instance_id,submission_date,age,sex,cluster_type,co_present_re,co_present_le\n"
        "P1,2026-01-01T10:00:00Z,55,Female,,Present,Absent\n"
        "P2,2026-01-02T10:00:00Z,61,Male,,Absent,Present\n"
    )
    fields = {field["key"]: field for field in payload["metadata_schema_json"]["fields"]}

    assert fields["patient_age_yrs"]["scope"] == "patient"
    assert fields["patient_age_yrs"]["type"] == "integer"
    assert fields["sex"]["master_hint"]["key"] == "sex"
    assert fields["laterality"]["options"] == [
        {"value": "OD", "label": "OD"},
        {"value": "OS", "label": "OS"},
    ]
    assert payload["mapper_draft"]["excluded_columns"] == [
        {"source_column": "cluster_type", "reason": "empty_column"}
    ]
    assert payload["privacy"] == {
        "rows_persisted": False,
        "row_samples_returned": False,
        "distinct_select_options_returned": True,
        "source_file_persisted": False,
    }


def test_inference_rejects_duplicate_headers_and_non_utf8():
    with pytest.raises(CsvInferenceError, match="duplicate header"):
        _infer("instance_id,age,age\nP1,50,51\n")
    with pytest.raises(CsvInferenceError, match="UTF-8"):
        infer_csv_configuration(io.BytesIO(b"instance_id\n\xff\n"), "bad.csv")


def test_harmonized_corneal_opacity_csv_contract_is_privacy_safe():
    path = Path(__file__).resolve().parents[2] / "backups" / "harmonized_dataset_with_dates.csv"
    with path.open("rb") as stream:
        payload = infer_csv_configuration(stream, path.name).payload

    assert payload["source"]["row_count"] == 5971
    assert payload["source"]["column_count"] == 54
    fields = {field["key"]: field for field in payload["metadata_schema_json"]["fields"]}
    assert fields["co_age_onset"]["type"] == "integer"
    assert fields["co_cause_other"]["type"] == "textarea"
    assert fields["co_treatment_barrier"]["type"] == "textarea"
    assert fields["laterality"]["master_hint"]["scope"] == "image"
    reserved = payload["mapper_draft"]["reserved_columns"]
    assert {item["source_column"] for item in reserved} == {
        "instance_id",
        "submission_date",
        "co_photo_re",
        "co_photo_le",
    }
    assert "rows" not in payload
    assert "samples" not in payload
