from utils.final_grade_basis import (
    FINAL_GRADE_UNRESOLVED,
    derive_final_grade_source,
    derive_final_grade_value,
    normalize_final_grade_basis,
)


def test_normalize_final_grade_basis_defaults_to_preference():
    assert normalize_final_grade_basis(None) == "preference"
    assert normalize_final_grade_basis("unknown") == "preference"


def test_double_match_uses_resident_arbitrator_without_regrade():
    value = derive_final_grade_value(
        "double_match",
        resident_grade="A",
        resident2_grade="B",
        arbitrator_grade="A",
        regrade_adj_grade=None,
    )

    assert value == "A"


def test_double_match_uses_regrade_and_excludes_arbitrator():
    value = derive_final_grade_value(
        "double_match",
        resident_grade="A",
        resident2_grade="B",
        arbitrator_grade="B",
        regrade_adj_grade="A",
    )

    assert value == "A"


def test_double_match_returns_unresolved_for_three_way_split():
    value = derive_final_grade_value(
        "double_match",
        resident_grade="A",
        resident2_grade="B",
        arbitrator_grade="C",
        regrade_adj_grade=None,
    )

    assert value == FINAL_GRADE_UNRESOLVED


def test_double_match_returns_unresolved_for_single_grade():
    value = derive_final_grade_value(
        "double_match",
        resident_grade="A",
        resident2_grade=None,
        arbitrator_grade=None,
        regrade_adj_grade=None,
    )

    assert value == FINAL_GRADE_UNRESOLVED


def test_preference_respects_existing_priority_order():
    value = derive_final_grade_value(
        "preference",
        resident_grade="A",
        resident2_grade="A",
        arbitrator_grade="B",
        regrade_adj_grade="C",
    )

    assert value == "C"


def test_preference_source_reports_priority_origin():
    source = derive_final_grade_source(
        "preference",
        resident_grade="A",
        resident2_grade="A",
        arbitrator_grade="B",
        regrade_adj_grade="C",
    )

    assert source == "Regrade Adj"


def test_double_match_source_reports_majority_origin():
    source = derive_final_grade_source(
        "double_match",
        resident_grade="A",
        resident2_grade="B",
        arbitrator_grade="A",
        regrade_adj_grade=None,
    )

    assert source == "Resident + Arbitrator"


def test_double_match_source_reports_no_majority():
    source = derive_final_grade_source(
        "double_match",
        resident_grade="A",
        resident2_grade="B",
        arbitrator_grade="C",
        regrade_adj_grade=None,
    )

    assert source == "No majority"
