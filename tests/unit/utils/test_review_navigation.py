from utils import review_navigation


class _FakeRow:
    def __init__(self, task_id: int):
        self.task_id = task_id


class _FakeResult:
    def fetchall(self):
        return [_FakeRow(2), _FakeRow(1)]


class _FakeDB:
    def __init__(self):
        self.sql = ""
        self.params = {}

    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params
        return _FakeResult()


def test_get_next_review_tasks_uses_discrepancy_filter_builder(monkeypatch):
    db = _FakeDB()
    captured_filters = {}

    def fake_build_query(_db, filters):
        captured_filters.update(filters)
        return (
            "mvw_image_listing_glaucoma_1_v2",
            "v.disease_id = :disease_id AND v.ai_models_json ? :ai_model_key",
            {"disease_id": filters["disease_id"], "ai_model_key": "1"},
            1,
        )

    monkeypatch.setattr(review_navigation, "build_discrepancy_filter_query", fake_build_query)

    result = review_navigation.get_next_review_tasks(
        db,
        current_task_id=3,
        disease_id=1,
        lab_unit_ids=[3],
        lab_unit_id=3,
        has_consensus="has_consensus",
        consensus_method="regrade",
        has_review="no",
        has_regrade="yes",
        has_arbitrator="yes",
        has_ai_grade="yes",
        ai_model_id=1,
        final_grade_basis="double_match",
        ai_grades=["Glaucoma", "Suspect"],
        ai_review_statuses=["missing"],
        regrade_grades=["Normal"],
        review_grades=["Suspect"],
        final_grades=["Normal"],
    )

    assert result["next_task_id"] == 2
    assert "FROM mvw_image_listing_glaucoma_1_v2 v" in db.sql
    assert "ORDER BY v.task_id DESC" in db.sql
    assert "AND v.task_id < :current_task_id" in db.sql
    assert db.params["current_task_id"] == 3
    assert db.params["limit"] == 2
    assert captured_filters["lab_unit_id"] == 3
    assert captured_filters["consensus_method"] == "regrade"
    assert captured_filters["has_regrade"] == "yes"
    assert captured_filters["has_arbitrator"] == "yes"
    assert captured_filters["final_grade_basis"] == "double_match"
    assert captured_filters["ai_review_status"] == ["missing"]
    assert captured_filters["regrade_grade"] == ["Normal"]
    assert captured_filters["review_grade"] == ["Suspect"]
    assert captured_filters["final_grade"] == ["Normal"]


def test_get_next_review_tasks_returns_none_when_no_materialized_view(monkeypatch):
    db = _FakeDB()

    def fake_build_query(_db, filters):
        return "", "", {}, None

    monkeypatch.setattr(review_navigation, "build_discrepancy_filter_query", fake_build_query)

    result = review_navigation.get_next_review_tasks(
        db,
        current_task_id=3,
        disease_id=1,
        lab_unit_ids=[3],
    )

    assert result == {"next_task_id": None, "next_after_task_id": None}
    assert db.sql == ""
