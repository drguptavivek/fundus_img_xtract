def test_admin_can_list_remidio_migration_projects(app, test_users):
    with app.test_client(user=test_users["admin"]) as client:
        response = client.get("/api/remidio-api/encounter-migrations/projects")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert isinstance(payload["projects"], list)


def test_admin_can_render_remidio_migration_workspace(app, test_users):
    with app.test_client(user=test_users["admin"]) as client:
        response = client.get("/admin/remidio-api/encounter-migration")

    assert response.status_code == 200
    assert b"Remidio API Encounter Migration" in response.data
    assert b"remidio-encounter-migration.js" in response.data


def test_non_admin_cannot_access_remidio_migration_projects(app, test_users):
    with app.test_client(user=test_users["resident"]) as client:
        response = client.get("/api/remidio-api/encounter-migrations/projects")

    assert response.status_code == 403


def test_preview_validates_json_shape(app, test_users):
    with app.test_client(user=test_users["admin"]) as client:
        response = client.post(
            "/api/remidio-api/encounter-migrations/preview",
            json={"source_project_id": 1},
        )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"]["message"] == "encounter_ids must be an array."
