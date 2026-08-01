from datetime import date

from services.wai_api_statistics import build_filters


def test_build_filters_normalizes_multiselect_values():
    filters = build_filters(
        disease_ids=["2", "bad", "2", "3"],
        project_ids=["", "4"],
        ai_model_ids=["1", "-1", "0"],
        result_types=["positive", "unknown", "NEGATIVE"],
        inference_statuses=["success", "failed", "done"],
        capture_start=date(2026, 7, 1),
        capture_end=date(2026, 7, 31),
    )

    assert filters.disease_ids == (2, 3)
    assert filters.project_ids == (4,)
    assert filters.ai_model_ids == (1,)
    assert filters.result_types == ("positive", "negative")
    assert filters.inference_statuses == ("success", "failed")
    assert filters.capture_start == date(2026, 7, 1)
    assert filters.capture_end == date(2026, 7, 31)
