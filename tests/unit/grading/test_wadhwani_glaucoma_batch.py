from __future__ import annotations

from models import AIModel, AIModelIntegration, Disease, LabUnit, Hospital, Job


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
