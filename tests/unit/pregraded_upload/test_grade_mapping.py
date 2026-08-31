from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from direct_uploads.pregraded_grades import (
    PendingImport,
    _auto_map_grade_values,
    _extract_rows,
    _resolve_grade_mapping,
)


def _pending(*, auto_mapping=None):
    return PendingImport(
        role="resident",
        hospital_id=1,
        lab_unit_id=2,
        disease_id=3,
        grader_user_id=4,
        rows=[
            {"image_name": "one.jpg", "grade_text": "Normal", "remarks": None},
            {"image_name": "two.jpg", "grade_text": "Legacy code A", "remarks": None},
        ],
        auto_mapping=auto_mapping or {},
    )


def test_unmatched_workbook_codes_remain_available_for_manual_mapping():
    options = {
        11: SimpleNamespace(id=11, impression="Normal"),
        12: SimpleNamespace(id=12, impression="Refer"),
    }

    automatic, unmatched = _auto_map_grade_values(
        options, ["Normal", "Legacy code A"]
    )

    assert automatic == {"Normal": 11}
    assert unmatched == ["Legacy code A"]


def test_manual_mapping_merges_with_preserved_automatic_matches():
    options = {
        11: SimpleNamespace(id=11, impression="Normal"),
        12: SimpleNamespace(id=12, impression="Refer"),
    }

    resolved = _resolve_grade_mapping(
        _pending(auto_mapping={"Normal": 11}),
        {"Legacy code A": 12},
        options,
    )

    assert resolved == {"Normal": 11, "Legacy code A": 12}


def test_missing_or_invalid_manual_mapping_still_denies():
    pending = _pending(auto_mapping={"Normal": 11})
    options = {11: SimpleNamespace(id=11, impression="Normal")}

    with pytest.raises(ValueError, match="No mapping provided"):
        _resolve_grade_mapping(pending, {}, options)
    with pytest.raises(ValueError, match="Invalid grade ID"):
        _resolve_grade_mapping(pending, {"Legacy code A": 999}, options)


def test_workbook_blank_image_target_denies_complete_import():
    frame = pd.DataFrame(
        {"image_name": ["one.jpg", None], "resident_grade": ["Normal", "Refer"]}
    )

    with pytest.raises(ValueError, match="row 3 has no image_name"):
        _extract_rows(frame, "resident")


def test_workbook_duplicate_normalized_target_denies_complete_import():
    frame = pd.DataFrame(
        {
            "image_name": ["One.JPG", " one.jpg "],
            "resident_grade": ["Normal", "Refer"],
        }
    )

    with pytest.raises(ValueError, match="duplicate image target"):
        _extract_rows(frame, "resident")
