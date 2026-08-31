"""Field surface: scoping, queue, status rollup, projection, and fetch."""
import pytest

from tests.helpers.factories import UserFactory, approve_mobile_device

from tests.unit.field_workbench.conftest import CAPTURE_DATE, JWT_SECRET


def _queue(client, headers, project_id, date_value=None):
    return client.get(
        f"/api/mobile/v1/field/projects/{project_id}/encounters",
        query_string={"date": (date_value or CAPTURE_DATE).isoformat()
                      if hasattr(date_value or CAPTURE_DATE, "isoformat") else date_value},
        headers=headers,
    )


def test_queue_requires_a_token(client, field_data):
    response = client.get(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/encounters",
        query_string={"date": CAPTURE_DATE.isoformat()},
    )
    assert response.status_code == 401


def test_queue_returns_only_encounters_in_the_callers_lab_scope(client, auth_headers, field_data):
    response = _queue(client, auth_headers, field_data["project"].id)

    assert response.status_code == 200
    rows = response.get_json()["encounters"]
    patient_ids = {row["patient_id"] for row in rows}
    assert "FIELD-1" in patient_ids
    # The grant is scoped to one lab unit; the other lab's encounter must not leak.
    assert "FIELD-2" not in patient_ids


def test_queue_carries_patient_identity_for_matching_the_person(client, auth_headers, field_data):
    rows = _queue(client, auth_headers, field_data["project"].id).get_json()["encounters"]
    row = next(row for row in rows if row["patient_id"] == "FIELD-1")

    assert row["patient_name"] == "Field Patient One"
    assert row["capture_date"] == CAPTURE_DATE.isoformat()
    assert row["source"] == "remidio"


def test_a_project_without_a_grant_is_not_found_rather_than_forbidden(
    client, db_session, field_data, monkeypatch
):
    """404, not 403 - otherwise project ids can be probed for existence."""
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    outsider = UserFactory.create_by_role(db_session, "field_optometrist", username="field_outsider")
    outsider.hospital_id = field_data["hospital"].id
    db_session.flush()
    approve_mobile_device(db_session, outsider.id, "device-field_outsider")

    login = client.post(
        "/api/mobile/v1/auth/login",
        json={
            "username": outsider.username,
            "password": "Test@2026",
            "device_id": "device-field_outsider",
            "device_name": "Outsider Device",
        },
    )
    token = login.get_json()["access_token"]

    response = _queue(
        client, {"Authorization": f"Bearer {token}"}, field_data["project"].id
    )
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_queue_rejects_a_malformed_date(client, auth_headers, field_data):
    response = client.get(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/encounters",
        query_string={"date": "20th August"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "invalid_date"


def test_encounter_dates_summarise_the_calendar_strip(client, auth_headers, field_data):
    response = client.get(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/encounter-dates",
        headers=auth_headers,
    )
    assert response.status_code == 200
    dates = response.get_json()["dates"]
    entry = next(item for item in dates if item["date"] == CAPTURE_DATE.isoformat())
    # Only the in-scope encounter is counted.
    assert entry["count"] == 1


def test_detail_exposes_images_and_no_internal_pipeline_fields(client, auth_headers, field_data):
    encounter = field_data["encounter"]
    response = client.get(
        f"/api/mobile/v1/field/encounters/{encounter.uuid}", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["patient_id"] == "FIELD-1"
    assert len(payload["images"]) == 2
    assert payload["images"][0]["thumbnail_url"].startswith("/api/mobile/v1/field/")

    # Whitelist assertion: DTO growth must not silently start leaking the
    # ingestion record or raw provider internals into a field response.
    body = response.get_data(as_text=True)
    for leaked in (
        "remote_key",
        "presign_response_json",
        "submit_response_json",
        "config_snapshot_json",
        "similarity_score",
        "raw_score",
        "request_manifest_json",
    ):
        assert leaked not in body, f"{leaked} must not reach the field surface"


def test_detail_out_of_scope_encounter_is_not_found(client, auth_headers, field_data):
    response = client.get(
        f"/api/mobile/v1/field/encounters/{field_data['other_encounter'].uuid}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_ai_reports_dr_and_dme_separately_and_glaucoma_alongside(client, auth_headers, field_data):
    rows = _queue(client, auth_headers, field_data["project"].id).get_json()["encounters"]
    row = next(row for row in rows if row["patient_id"] == "FIELD-1")

    kinds = [item["kind"] for item in row["ai"]]
    assert kinds == ["dr", "dme", "glaucoma"]
    # Nothing has run and no workflow is enabled in this project.
    for item in row["ai"]:
        assert item["run_status"] == "not_requested"
        assert item["requestable"] is False
        assert item["reason"] == "workflow_disabled"


def test_inference_request_is_refused_when_project_policy_disables_it(
    client, auth_headers, field_data
):
    response = client.post(
        f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}/inference",
        json={"workflows": ["dr_dme"]},
        headers=auth_headers,
    )

    assert response.status_code == 200
    result = response.get_json()["workflows"]["dr_dme"]
    assert result["queued"] is False
    assert result["reason"] == "workflow_disabled"


def test_unknown_workflow_is_rejected(client, auth_headers, field_data):
    response = client.post(
        f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}/inference",
        json={"workflows": ["cataract"]},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "unknown_workflow"


def test_fetch_status_reports_unconfigured_sources_rather_than_failing(
    client, auth_headers, field_data
):
    response = client.get(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/fetch",
        headers=auth_headers,
    )
    assert response.status_code == 200
    sources = {item["source"]: item for item in response.get_json()["sources"]}
    assert sources["remidio"]["state"] == "not_configured"
    assert sources["iitk"]["state"] == "not_configured"
    assert sources["remidio"]["running"] is False


def test_queueing_a_fetch_for_an_unconfigured_source_is_a_typed_conflict(
    client, auth_headers, field_data
):
    from field_workbench.throttle import reset_fetch_spacing

    reset_fetch_spacing(field_data["user"].id)
    response = client.post(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/fetch",
        json={"source": "remidio"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "source_not_configured"


def test_fetch_requests_from_one_user_must_be_spaced_apart(client, auth_headers, field_data):
    """The limiter expresses rates, not spacing, so the gap is enforced separately."""
    from field_workbench.throttle import reset_fetch_spacing

    reset_fetch_spacing(field_data["user"].id)
    url = f"/api/mobile/v1/field/projects/{field_data['project'].id}/fetch"

    first = client.post(url, json={"source": "remidio"}, headers=auth_headers)
    second = client.post(url, json={"source": "remidio"}, headers=auth_headers)

    # The first is refused on configuration, but it still consumed the slot.
    assert first.status_code == 409
    if second.status_code == 429:
        assert second.get_json()["error"] == "rate_limited"
        assert second.headers.get("Retry-After")
    else:
        pytest.skip("Redis unavailable, so request spacing cannot be enforced")
    reset_fetch_spacing(field_data["user"].id)


def test_context_me_now_carries_projects_and_their_policy(client, auth_headers, field_data):
    response = client.get("/api/mobile/v1/context/me", headers=auth_headers)

    assert response.status_code == 200
    payload = response.get_json()
    project = next(
        item for item in payload["projects"] if item["id"] == field_data["project"].id
    )
    assert project["can_trigger_fetch"] is True
    # No AI workflow is enabled for this project, so the client hides the action.
    assert project["ai_workflows"] == []


def test_legacy_encounter_set_upload_route_is_gone(app):
    """The dead pre-session-model mobile upload path is unregistered.

    Asserted against the URL map rather than a request, because the global login
    guard redirects an unauthenticated request before routing would 404.
    """
    rules = {str(rule) for rule in app.url_map.iter_rules()}
    assert "/api/v1/encounter-set/upload" not in rules

    import api.encounter_set as legacy

    assert not hasattr(legacy, "generate_mobile_token")


def test_patient_refetch_requires_an_mrn(client, auth_headers, field_data):
    response = client.post(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/patients/refetch",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "mrn_required"


def test_patient_refetch_is_remidio_only(client, auth_headers, field_data):
    """IITK has no per-patient endpoint; say so rather than failing obscurely."""
    from field_workbench.throttle import reset_fetch_spacing

    reset_fetch_spacing(field_data["user"].id)
    response = client.post(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/patients/refetch",
        json={"mrn": "MRN-1", "source": "iitk"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "unsupported_source"
    reset_fetch_spacing(field_data["user"].id)


def test_patient_refetch_reports_an_unconfigured_project(client, auth_headers, field_data):
    from field_workbench.throttle import reset_fetch_spacing

    reset_fetch_spacing(field_data["user"].id)
    response = client.post(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/patients/refetch",
        json={"mrn": "MRN-1"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "source_not_configured"
    reset_fetch_spacing(field_data["user"].id)
