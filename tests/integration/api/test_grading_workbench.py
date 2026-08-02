from tests.helpers.test_factories import TestDataFactory


def test_eligible_grader_can_resolve_standalone_task_workspace(
    app,
    db_session,
    test_users,
    core_test_data,
):
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        state="pending",
        image_name="standalone-workbench.jpg",
    )

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["schema_version"] == 1
    assert payload["target"] == {
        "type": "task",
        "ref": task.uuid,
        "slot": "resident",
    }
    assert payload["task"]["uuid"] == task.uuid
    assert payload["task"]["state"] == "pending"
    assert payload["task"]["disease"] == {
        "id": core_test_data["glaucoma"].id,
        "name": core_test_data["glaucoma"].name,
    }
    assert payload["image"]["uuid"] == task.encounter_file.uuid
    assert payload["image"]["url"].endswith(
        f"/media/img/{task.encounter_file.uuid}"
    )
    assert payload["capabilities"] == {
        "view": True,
        "annotate": False,
        "submit": False,
    }
    assert isinstance(payload["context_revision"], str)
    assert len(payload["context_revision"]) == 64


def test_grader_without_task_grant_cannot_resolve_workspace(
    app,
    db_session,
    test_users,
    core_test_data,
):
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        state="pending",
    )

    with app.test_client(user=test_users["ophthalmologist"]) as client:
        response = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert response.status_code == 403
    assert response.get_json() == {
        "error": "access_denied",
        "message": "You are not eligible to view this grading slot.",
    }


def test_standalone_workbench_page_uses_vite_assets_and_workspace_api(
    app,
    db_session,
    test_users,
    core_test_data,
    monkeypatch,
):
    from grading import workbench as page_routes

    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        state="pending",
    )
    monkeypatch.setattr(
        page_routes,
        "get_workbench_assets",
        lambda: {
            "script": "grading-workbench/assets/workbench.js",
            "styles": ["grading-workbench/assets/workbench.css"],
        },
    )

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(
            f"/grading/workbench/task/{task.uuid}/resident"
        )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="grading-workbench-root"' in html
    assert (
        f'data-workspace-url="/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"'
        in html
    )
    assert '/static/grading-workbench/assets/workbench.js' in html
    assert '/static/grading-workbench/assets/workbench.css' in html
    assert "partials/_grading_card.html" not in html
