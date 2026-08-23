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


def test_build_discrepancy_filter_query_filters_selected_model_human_review(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    _mv_name, where_sql, params, selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "has_ai_grade": "yes",
            "ai_model_id": ["7"],
            "has_human_review": "yes",
        },
    )

    assert selected_ai_model_id == 7
    assert params["ai_model_key"] == "7"
    assert "v.has_review = TRUE OR" in where_sql
    assert "ai_review_status" in where_sql
    assert "ai_review_comment" in where_sql
    assert "BTRIM(v.review_comment)" in where_sql


def test_build_discrepancy_filter_query_filters_selected_model_not_human_reviewed(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    _mv_name, where_sql, _params, _selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "has_ai_grade": "yes",
            "ai_model_id": ["7"],
            "has_human_review": "no",
        },
    )

    assert "NOT (v.has_review = TRUE OR" in where_sql
    assert "ai_review_status" in where_sql
    assert "ai_review_comment" in where_sql


def test_build_discrepancy_filter_query_filters_any_model_human_review(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    _mv_name, where_sql, _params, selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "has_ai_grade": "yes",
            "has_human_review": "yes",
        },
    )

    assert selected_ai_model_id is None
    assert "EXISTS (SELECT 1 FROM jsonb_each(v.ai_models_json) kv" in where_sql
    assert "COALESCE(NULLIF(kv.value->>'ai_review_status', ''), '') <> ''" in where_sql
    assert "kv.value->>'ai_review_comment'" in where_sql


def test_build_discrepancy_filter_query_includes_review_grade_without_ai_filter(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    _mv_name, where_sql, _params, _selected_ai_model_id = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {
            "disease_id": 1,
            "allowed_lab_units": [1],
            "has_human_review": "yes",
        },
    )

    assert "v.has_review = TRUE OR" in where_sql
    assert "kv.value->>'ai_review_status'" in where_sql


def test_build_discrepancy_filter_query_supports_review_status_cohorts(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")

    clauses = {}
    for status in ("unreviewed", "human", "ai", "both", "any"):
        _mv, clauses[status], _params, _model = discrepancy_filters.build_discrepancy_filter_query(
            _FakeDB(),
            {"disease_id": 1, "allowed_lab_units": [1], "has_human_review": status},
        )

    assert "NOT (v.has_review = TRUE OR" in clauses["unreviewed"]
    assert "AND NOT EXISTS" in clauses["human"]
    assert "NOT (v.has_review = TRUE OR" in clauses["ai"]
    assert "AND EXISTS" in clauses["both"]
    assert "OR EXISTS" in clauses["any"]


def test_build_discrepancy_filter_query_scopes_uploaded_task_ids(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")
    _mv, where_sql, params, _model = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {"disease_id": 1, "allowed_lab_units": [1], "task_ids": [9, 4]},
    )

    assert "v.task_id = ANY(:task_ids)" in where_sql
    assert params["task_ids"] == [9, 4]


def test_build_discrepancy_filter_query_scopes_source_project(monkeypatch):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")
    _mv, where_sql, params, _model = discrepancy_filters.build_discrepancy_filter_query(
        _FakeDB(),
        {"disease_id": 1, "project_id": 8, "allowed_lab_units": [1]},
    )

    assert "selected_project_task.id = v.task_id" in where_sql
    assert "selected_task_encounter.project_id" in where_sql
    assert "selected_task_set_image.project_id" in where_sql
    assert "selected_set_image_encounter.project_id" in where_sql
    assert "selected_task_image.project_id" in where_sql
    assert "selected_task_direct.project_id" in where_sql
    assert params["project_id"] == 8


def test_build_discrepancy_filter_query_accepts_scoped_project_role_grants(monkeypatch):
    monkeypatch.setattr(
        discrepancy_filters,
        "get_mv_name_for_disease",
        lambda db, disease_id: "mv_test",
    )

    _mv_name, where_sql, params, _selected_ai_model_id = (
        discrepancy_filters.build_discrepancy_filter_query(
            _FakeDB(),
            {
                "disease_id": 1,
                "allowed_lab_units": [4],
                "project_capability_user_id": 22,
                "project_capability_role_names": ["discrepancy_reviewer"],
            },
        )
    )

    assert "FROM project_role_grants prg" in where_sql
    assert "prg.scope_type = 'project'" in where_sql
    assert "prg.lab_unit_id = project_task.lab_unit_id" in where_sql
    assert "scope_lab.hospital_id = prg.hospital_id" in where_sql
    assert params["project_capability_user_id"] == 22
    assert params["project_capability_role_names"] == ["discrepancy_reviewer"]


# --- project-wide scope for dataset curation --------------------------------
# The curation screen reads a materialized view through raw SQL rather than
# the ORM, so the rule expressed in authz.policies for dataset.curation.*
# has to be asserted against the generated SQL as well.


def _curation_sql(monkeypatch, **overrides):
    monkeypatch.setattr(discrepancy_filters, "get_mv_name_for_disease", lambda db, disease_id: "mv_test")
    filters = {
        "disease_id": 1,
        "allowed_lab_units": [1],
        "project_capability_columns": [],
        "project_capability_role_names": ["dataset_creator"],
        "project_capability_require_project_scope": True,
        "allow_classical_capability": True,
        "project_capability_user_id": 7,
    }
    filters.update(overrides)
    _mv, where_sql, params, _ai = discrepancy_filters.build_discrepancy_filter_query(_FakeDB(), filters)
    return where_sql, params


def test_curation_accepts_only_project_wide_grants(monkeypatch):
    where_sql, params = _curation_sql(monkeypatch)
    assert "prg.scope_type = 'project'" in where_sql
    assert "prg.scope_type = 'lab_unit'" not in where_sql, "a lab-scoped grant must not curate a project"
    assert "prg.scope_type = 'hospital'" not in where_sql
    assert params["project_capability_role_names"] == ["dataset_creator"]


def test_curation_still_admits_rows_that_belong_to_no_project(monkeypatch):
    """Unowned rows keep the classical lab-unit rule."""
    where_sql, _ = _curation_sql(monkeypatch)
    assert "IS NULL OR" in where_sql
    assert "v.task_lab_unit_id = ANY(:allowed_lab_units)" in where_sql


def test_curation_does_not_consult_legacy_capability_rows(monkeypatch):
    where_sql, _ = _curation_sql(monkeypatch)
    assert "project_encounter_set_permissions" not in where_sql


def test_other_surfaces_keep_accepting_narrower_grants(monkeypatch):
    """Only actions that opt in are restricted to project-wide grants."""
    where_sql, _ = _curation_sql(
        monkeypatch,
        project_capability_role_names=["discrepancy_reviewer"],
        project_capability_require_project_scope=False,
    )
    assert "prg.scope_type = 'lab_unit'" in where_sql
    assert "prg.scope_type = 'hospital'" in where_sql
