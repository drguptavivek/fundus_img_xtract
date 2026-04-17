from utils import discrepancy_filters


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [type("Row", (), {"impression": "A"})(), type("Row", (), {"impression": "B"})()]


class _FakeDB:
    def query(self, *args, **kwargs):
        return _FakeQuery()


def test_build_discrepancy_filter_query_uses_preference_expression(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    mv_name, where_sql, params, _selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "final_grade": ["A"],
            "final_grade_basis": "preference",
        },
    )

    assert mv_name == "mv_test"
    assert "regrade_adj_grade_name" in where_sql
    assert params["final_grades"] == ["A"]


def test_build_discrepancy_filter_query_allows_unresolved_for_double_match(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    mv_name, where_sql, params, _selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "final_grade": ["Unresolved"],
            "final_grade_basis": "double_match",
        },
    )

    assert mv_name == "mv_test"
    assert "Unresolved" in params["final_grades"]
    assert "regrade_adj_grade_name" in where_sql
    assert "arbitrator_grade_name" in where_sql
