from utils import review_navigation


class _FakeRow:
    def __init__(self, task_id: int):
        self.task_id = task_id


class _FakeResult:
    def fetchall(self):
        return [_FakeRow(3), _FakeRow(2), _FakeRow(1)]


class _FakeDB:
    def __init__(self):
        self.sql = ""
        self.params = {}

    def get(self, model, disease_id):
        return type("DiseaseRow", (), {"name": "Glaucoma"})()

    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params
        return _FakeResult()


def test_get_next_review_tasks_filters_missing_ai_review_status():
    db = _FakeDB()

    result = review_navigation.get_next_review_tasks(
        db,
        current_task_id=3,
        disease_id=1,
        lab_unit_ids=[3],
        has_ai_grade="yes",
        ai_model_id=1,
        ai_grades=["Glaucoma", "Suspect"],
        ai_review_statuses=["missing"],
    )

    assert result["next_task_id"] == 2
    assert "glaucoma_grading_details_json" in db.sql
    assert "elem->>'role_slot' = 'ai'" in db.sql
    assert "COALESCE(NULLIF(elem->>'ai_review_status', ''), '') = ''" in db.sql
    assert "ai_review_statuses" not in db.params


def test_get_next_review_tasks_combines_missing_and_explicit_ai_review_status():
    db = _FakeDB()

    review_navigation.get_next_review_tasks(
        db,
        current_task_id=3,
        disease_id=1,
        lab_unit_ids=[3],
        has_ai_grade="yes",
        ai_review_statuses=["ok", "missing"],
    )

    assert "elem->>'ai_review_status' = ANY(:ai_review_statuses)" in db.sql
    assert " OR " in db.sql
    assert db.params["ai_review_statuses"] == ["ok"]
