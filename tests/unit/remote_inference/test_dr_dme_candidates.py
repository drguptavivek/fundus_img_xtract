from types import SimpleNamespace

from remote_inference.dr_dme import ALLOWED_PAGE_SIZES, CandidateFilters, validate_selection_count
from remote_inference.dr_dme.candidates import _dr_report_summary, _matches_eligibility_filter


def test_candidate_filters_normalize_page_size_and_report_value():
    invalid = CandidateFilters(
        project_id=2,
        dr_report="unknown",
        page=0,
        page_size=26,
    ).normalized()
    selected = CandidateFilters(project_id=2, page=3, page_size=100, dr_report="present").normalized()

    assert ALLOWED_PAGE_SIZES == (25, 50, 75, 100)
    assert invalid.page == 1
    assert invalid.page_size == 25
    assert invalid.dr_report == ""
    assert invalid.eligibility == "eligible"
    assert selected.page == 3
    assert selected.page_size == 100
    assert selected.dr_report == "present"
    assert validate_selection_count(100) is None
    assert validate_selection_count(101) == "Select between 1 and 100 EncounterSets."


def test_candidate_filters_support_operational_eligibility_categories():
    one_eye = SimpleNamespace(
        eligible=False,
        is_verified=True,
        is_monocular=False,
        eye_counts={"right": 2, "left": 0},
    )
    monocular = SimpleNamespace(
        eligible=True,
        is_verified=True,
        is_monocular=True,
        eye_counts={"right": 2, "left": 0},
    )
    unverified = SimpleNamespace(
        eligible=False,
        is_verified=False,
        is_monocular=False,
        eye_counts={"right": 1, "left": 1},
    )

    assert _matches_eligibility_filter(monocular, "eligible") is True
    assert _matches_eligibility_filter(unverified, "eligible") is False
    assert _matches_eligibility_filter(unverified, "not_verified") is True
    assert _matches_eligibility_filter(one_eye, "binocular_one_eye") is True
    assert _matches_eligibility_filter(monocular, "binocular_one_eye") is False
    assert _matches_eligibility_filter(one_eye, "any") is True


def test_dr_report_summary_detects_normalized_report_independent_of_result():
    encounter = SimpleNamespace(encounter_set_attachments=[SimpleNamespace(
        original_filename="screening.pdf",
        metadata_json={"ocr": {"status": "completed", "dr_report": {"result": "No DR"}}},
    )])

    summary = _dr_report_summary(encounter)

    assert summary == {
        "status": "completed",
        "result": "No DR",
        "attachment_filename": "screening.pdf",
    }
