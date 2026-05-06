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


def test_build_discrepancy_filter_query_filters_missing_ai_review_status(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    mv_name, where_sql, params, selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "has_ai_grade": "yes",
            "ai_review_status": ["missing"],
        },
    )

    assert mv_name == "mv_test"
    assert selected_ai_model_id is None
    assert "jsonb_each(v.ai_models_json)" in where_sql
    assert "COALESCE(NULLIF(kv.value->>'ai_review_status', ''), '') = ''" in where_sql
    assert "ai_review_statuses" not in params


def test_build_discrepancy_filter_query_combines_missing_and_explicit_ai_review_status(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    _mv_name, where_sql, params, selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "has_ai_grade": "yes",
            "ai_model_id": ["7"],
            "ai_review_status": ["ok", "missing"],
        },
    )

    assert selected_ai_model_id == 7
    assert "(v.ai_models_json -> :ai_model_key) ->> 'ai_review_status' = ANY(:ai_review_statuses)" in where_sql
    assert "COALESCE(NULLIF((v.ai_models_json -> :ai_model_key) ->> 'ai_review_status', ''), '') = ''" in where_sql
    assert " OR " in where_sql
    assert params["ai_review_statuses"] == ["ok"]
