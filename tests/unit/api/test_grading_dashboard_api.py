from grading.dashboard_service import DailyTrendDTO, HistoryPageDTO


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def test_my_grading_eligibility_api_separates_sources(
    client, resident_user, monkeypatch
):
    _authenticate(client, resident_user)
    expected = {
        "non_project": [{"disease": {"id": 1, "name": "DR"}}],
        "project": [{"project": {"id": 3, "title": "Screening"}}],
    }
    observed = {}

    def fake_eligibility(_db, *, user_id):
        observed["user_id"] = user_id
        return expected

    monkeypatch.setattr(
        "api.grading_dashboard.grader_eligibility_dto", fake_eligibility
    )

    response = client.get("/api/grading/me/eligibility")

    assert response.status_code == 200
    assert observed["user_id"] == resident_user.id
    assert response.get_json() == {"success": True, "eligibility": expected}


def test_my_grading_history_api_passes_filters_and_pagination(
    client, resident_user, monkeypatch
):
    _authenticate(client, resident_user)
    observed = {}
    history = HistoryPageDTO(
        selected_date="2026-08-09",
        requested_date="2026-08-09",
        used_latest_fallback=False,
        history_type="encounter_set",
        disease_id=7,
        page=2,
        per_page=20,
        total_cards=21,
        total_pages=2,
        total_tasks=44,
        total_images=12,
        previous_date="2026-08-08",
        next_date=None,
        available_diseases=({"id": 7, "name": "DR"},),
        trends=(DailyTrendDTO(date="2026-08-09", task_count=44, image_count=12),),
        items=(),
    )

    def fake_history(_db, **kwargs):
        observed.update(kwargs)
        return history

    monkeypatch.setattr("api.grading_dashboard.grading_history_page", fake_history)

    response = client.get(
        "/api/grading/me/history?date=2026-08-09&type=encounter_set"
        "&disease_id=7&page=2&per_page=20"
    )

    assert response.status_code == 200
    assert observed == {
        "user_id": resident_user.id,
        "requested_date": "2026-08-09",
        "history_type": "encounter_set",
        "disease_id": 7,
        "page": 2,
        "per_page": 20,
    }
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["history"]["total_tasks"] == 44
    assert payload["history"]["trends"][0]["image_count"] == 12


def test_my_grading_history_api_returns_validation_error(
    client, resident_user
):
    _authenticate(client, resident_user)

    response = client.get("/api/grading/me/history?date=not-a-date")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_history_filter"
