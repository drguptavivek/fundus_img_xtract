from datetime import datetime, timezone
from unittest.mock import patch

from flask import render_template
from sqlalchemy.dialects import postgresql

from analytics.public_kpis.dto import PublicKpisDTO
from analytics.public_kpis.service import _disease_task_counts_query
from app import PUBLIC_SESSION_PATHS, PUBLIC_SESSION_PREFIXES


def _kpis() -> PublicKpisDTO:
    return PublicKpisDTO(
        total_images=30,
        zip_images=10,
        direct_images=8,
        encounter_set_images=12,
        total_encounters=9,
        zip_encounters=4,
        encounter_set_encounters=5,
        total_ai_gradings=6,
        total_gradings=18,
        active_projects=3,
        total_tasks=21,
        disease_task_counts={"DR": 11, "Glaucoma": 7},
        generated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def test_public_kpis_is_an_exact_public_session_path():
    assert "/api/public_kpis" in PUBLIC_SESSION_PATHS
    assert "/api/" not in PUBLIC_SESSION_PREFIXES
    assert "/api/analytics/" not in PUBLIC_SESSION_PREFIXES


def test_public_kpis_returns_json_to_anonymous_clients(app):
    with patch("api.public_kpis.get_public_kpis", return_value=_kpis()):
        response = app.test_client().get("/api/public_kpis")

    assert response.status_code == 200
    assert response.is_json
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["total_images"] == 30
    assert payload["data"]["disease_task_counts"] == {"DR": 11, "Glaucoma": 7}
    assert set(payload["data"]) == {
        "total_images",
        "zip_images",
        "direct_images",
        "encounter_set_images",
        "total_encounters",
        "zip_encounters",
        "encounter_set_encounters",
        "total_ai_gradings",
        "total_gradings",
        "active_projects",
        "total_tasks",
        "disease_task_counts",
        "generated_at",
    }


def test_public_pages_render_lightweight_htmx_shells(app):
    with app.test_request_context("/"):
        homepage = render_template("home.html")
    with app.test_request_context("/analytics"):
        analytics_page = render_template("public/analytics.html")

    assert 'hx-get="/api/public_kpis"' in homepage
    assert 'hx-get="/api/public_kpis"' in analytics_page


def test_public_kpis_returns_shared_fragment_for_htmx(app):
    with patch("api.public_kpis.get_public_kpis", return_value=_kpis()):
        response = app.test_client().get(
            "/api/public_kpis",
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"Total Images" in response.data
    assert b"Image-level Tasks by Disease" in response.data
    assert b"Encounter-level and unified EncounterSet tasks are excluded" in response.data


def test_public_kpis_executes_against_test_database(app):
    response = app.test_client().get("/api/public_kpis")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["total_images"] == (
        payload["zip_images"]
        + payload["direct_images"]
        + payload["encounter_set_images"]
    )
    assert payload["total_encounters"] == (
        payload["zip_encounters"] + payload["encounter_set_encounters"]
    )
    assert payload["total_ai_gradings"] <= payload["total_gradings"]
    assert all(count >= 0 for count in payload["disease_task_counts"].values())


def test_disease_task_query_excludes_encounter_and_unified_targets():
    sql = str(
        _disease_task_counts_query().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "grading_tasks.patient_encounter_id" not in sql
    assert "grading_tasks.encounter_file_id IS NOT NULL" in sql
    assert "grading_tasks.direct_image_upload_id IS NOT NULL" in sql
    assert "grading_tasks.encounter_set_image_id IS NOT NULL" in sql
    assert "encounter_set_grading_scopes.link_role != 'unified'" in sql
