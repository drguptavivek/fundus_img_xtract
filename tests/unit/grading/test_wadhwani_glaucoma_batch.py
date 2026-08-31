from __future__ import annotations

from types import SimpleNamespace

from models import AIModel, AIModelIntegration, Disease, LabUnit, Hospital, Job
from utils.wadhwani_glaucoma_selector import (
    MAX_MANUAL_WADHWANI_BATCH,
    filter_still_eligible_task_ids,
    list_eligible_wadhwani_glaucoma_tasks,
)


def _seed_linked_wadhwani_model(db_session):
    model = AIModel(name="wai_glaucoma_ver1", version="1")
    db_session.add(model)
    db_session.flush()
    integration = AIModelIntegration(
        ai_model_id=model.id,
        provider="wadhwani_glaucoma",
        is_enabled=True,
        client_id="cid",
        bearer_token="token",
    )
    db_session.add(integration)
    db_session.flush()
    return model


def test_wadhwani_batch_page_renders_for_admin(client, login_user, db_session):
    _seed_linked_wadhwani_model(db_session)
    hospital = Hospital(name="AIIMS Test")
    db_session.add(hospital)
    db_session.flush()
    lab_unit = LabUnit(name="Community Ophthalmology", hospital=hospital)
    db_session.add(lab_unit)
    db_session.flush()

    login_user("test_admin", "Test@2026")

    response = client.get("/grading/wadhwani-glaucoma-inference/")

    assert response.status_code == 200
    assert b"Wadhwani Glaucoma Inference" in response.data
    assert b"Source Type" in response.data
    assert b">ZIP</option>" in response.data
    assert b">Direct</option>" in response.data
    assert b"Pregraded" in response.data
    assert b"Maximum 100 tasks" in response.data
    assert b"Project-based Inference" in response.data

    # Global administration does not imply project clinical authority.
    project_response = client.get("/uploads/encountersets/wadhwani_inference")
    assert project_response.status_code == 403


def test_wadhwani_job_pages_poll_every_five_seconds(client, login_user, db_session):
    db_session.add(
        Job(
            token="image-job-token",
            status="queued",
            upload_type="wadhwani_glaucoma_inference",
        )
    )
    db_session.flush()
    login_user("test_admin", "Test@2026")

    image_job = client.get("/grading/wadhwani-glaucoma-inference/jobs/image-job-token")
    project_job = client.get(
        "/uploads/encountersets/wadhwani_inference/jobs/project-job-token"
    )

    assert image_job.status_code == 200
    assert b'hx-trigger="load, every 5s"' in image_job.data
    # Project jobs require an existing job plus current project authority.
    assert project_job.status_code == 404


def test_wadhwani_batch_submit_creates_job_and_enqueues_task(client, login_user, db_session, monkeypatch):
    _seed_linked_wadhwani_model(db_session)
    hospital = Hospital(name="AIIMS Submit")
    db_session.add(hospital)
    db_session.flush()
    lab_unit = LabUnit(name="Community Ophthalmology", hospital=hospital)
    db_session.add(lab_unit)
    db_session.flush()

    captured: dict[str, object] = {}

    def _fake_enqueue(task_name, *args, **kwargs):
        captured["task_name"] = task_name
        captured["args"] = args
        captured["kwargs"] = kwargs
        return None

    monkeypatch.setattr("grading.wadhwani_glaucoma_inference.enqueue_task", _fake_enqueue)
    monkeypatch.setattr(
        "grading.wadhwani_glaucoma_inference.filter_still_eligible_task_ids",
        lambda *args, **kwargs: [101, 102],
    )

    login_user("test_admin", "Test@2026")

    response = client.post(
        "/grading/wadhwani-glaucoma-inference/run",
        data={"selected_task_ids": ["101", "102"]},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert "/grading/wadhwani-glaucoma-inference/jobs/" in location
    assert captured["task_name"] == "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task"
    assert list(captured["args"][1]) == [101, 102]

    job = db_session.query(Job).filter(Job.upload_type == "wadhwani_glaucoma_inference").one()
    assert job.status == "queued"

    queued_status = client.get(f"{location}/status")
    assert queued_status.status_code == 200

    job.status = "done"
    db_session.flush()

    done_status = client.get(f"{location}/status")
    assert done_status.status_code == 286
    assert b'data-job-done="true"' in done_status.data


def test_encounter_set_terminal_job_status_stops_htmx_polling(client, login_user, db_session):
    job = Job(
        token="terminal-encounter-wadhwani-job",
        status="partial",
        upload_type="encounter_set_wadhwani_inference",
    )
    db_session.add(job)
    db_session.flush()
    login_user("test_admin", "Test@2026")

    response = client.get(
        "/uploads/encountersets/wadhwani_inference/jobs/terminal-encounter-wadhwani-job/status"
    )

    assert response.status_code == 286
    assert b'data-job-done="true"' in response.data


def test_wadhwani_batch_rejects_more_than_100_tasks(client, login_user, monkeypatch):
    enqueue_called = False

    def _unexpected_enqueue(*args, **kwargs):
        nonlocal enqueue_called
        enqueue_called = True

    monkeypatch.setattr("grading.wadhwani_glaucoma_inference.enqueue_task", _unexpected_enqueue)
    login_user("test_admin", "Test@2026")

    response = client.post(
        "/grading/wadhwani-glaucoma-inference/run",
        data={"selected_task_ids": [str(task_id) for task_id in range(1, 102)]},
        follow_redirects=False,
    )

    assert MAX_MANUAL_WADHWANI_BATCH == 100
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/grading/wadhwani-glaucoma-inference/")
    assert enqueue_called is False


def test_submit_revalidation_accepts_zip_direct_and_pregraded_tasks(monkeypatch):
    captured: dict[str, object] = {}

    class _Rows:
        @staticmethod
        def all():
            return [(12,)]

    class _DB:
        @staticmethod
        def execute(statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return _Rows()

    monkeypatch.setattr(
        "utils.wadhwani_glaucoma_selector.get_glaucoma_disease",
        lambda db: SimpleNamespace(id=1),
    )
    monkeypatch.setattr(
        "utils.wadhwani_glaucoma_selector.get_mv_name_for_disease",
        lambda db, disease_id: "mv_test_glaucoma",
    )

    eligible = filter_still_eligible_task_ids(
        _DB(),
        ai_model_id=1,
        allowed_lab_unit_ids=[3],
        task_ids=[12, 13],
    )

    assert eligible == [12]
    assert "v.upload_type = 'ZIP'" in captured["sql"]
    assert "v.upload_type IN ('Direct', :pregraded_upload_type)" in captured["sql"]
    assert "v.direct_image_upload_id IS NOT NULL" in captured["sql"]
    assert captured["params"]["pregraded_upload_type"] == "Pregraded"


def test_pregraded_preview_uses_separate_direct_image_source(monkeypatch):
    captured: dict[str, object] = {}

    class _Rows:
        @staticmethod
        def fetchall():
            return []

    class _DB:
        @staticmethod
        def execute(statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return _Rows()

    monkeypatch.setattr(
        "utils.wadhwani_glaucoma_selector.get_glaucoma_disease",
        lambda db: SimpleNamespace(id=1),
    )
    monkeypatch.setattr(
        "utils.wadhwani_glaucoma_selector.get_mv_name_for_disease",
        lambda db, disease_id: "mv_test_glaucoma",
    )

    tasks = list_eligible_wadhwani_glaucoma_tasks(
        _DB(),
        ai_model_id=1,
        allowed_lab_unit_ids=[3],
        filters={"source_type": "pregraded", "limit": "100"},
    )

    assert tasks == []
    assert "v.upload_type = :pregraded_upload_type" in captured["sql"]
    assert "v.direct_image_upload_id IS NOT NULL" in captured["sql"]
    assert captured["params"]["pregraded_upload_type"] == "Pregraded"
    assert captured["params"]["limit"] == 100
