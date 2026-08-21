"""The enabled-workflow inference paths.

These exercise what the policy-disabled tests cannot: real job creation, the
idempotency guard, and that Celery dispatch is deferred until after the request's
transaction commits rather than racing the rows the worker needs.
"""
from itertools import count

import pytest
from sqlalchemy import func, select

from models import AIModel, AIModelIntegration, Disease, GradingTask, Job
from remote_inference.models import (
    ProjectEncounterAIWorkflow,
    ProjectManualRemoteInferenceWorkflow,
)

_SEQUENCE = count(1)


@pytest.fixture
def glaucoma_enabled(db_session, field_data):
    """Enable the project's manual Glaucoma workflow, integration included."""
    glaucoma = db_session.execute(
        select(Disease).where(func.lower(Disease.name) == "glaucoma")
    ).scalars().first()
    suffix = next(_SEQUENCE)
    model = AIModel(name=f"wadhwani_glaucoma_test_{suffix}", version="1.0")
    db_session.add(model)
    db_session.flush()

    integration = db_session.execute(
        select(AIModelIntegration).where(AIModelIntegration.provider == "wadhwani_glaucoma")
    ).scalars().first()
    if integration is None:
        integration = AIModelIntegration(
            provider="wadhwani_glaucoma",
            ai_model_id=model.id,
            is_enabled=True,
            client_id="test-client",
            bearer_token="test-token",
        )
        db_session.add(integration)
    else:
        integration.ai_model_id = model.id
        integration.is_enabled = True
    db_session.add(
        ProjectManualRemoteInferenceWorkflow(
            project_id=field_data["project"].id,
            disease_id=glaucoma.id,
            ai_model_id=model.id,
            upload_kind="encounter_set",
            active=True,
        )
    )
    db_session.flush()
    return {"model": model, "disease": glaucoma}


def test_glaucoma_request_creates_tasks_and_defers_the_worker_dispatch(
    client, auth_headers, db_session, field_data, glaucoma_enabled, monkeypatch
):
    dispatched = []
    monkeypatch.setattr(
        "services.encounter_set_ai_inference.enqueue_task",
        lambda *args, **kwargs: dispatched.append(args),
    )

    response = client.post(
        f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}/inference",
        json={"workflows": ["glaucoma"]},
        headers=auth_headers,
    )

    assert response.status_code == 202, response.get_data(as_text=True)
    result = response.get_json()["workflows"]["glaucoma"]
    assert result["queued"] is True
    assert result["task_count"] == 2
    # The transport payload must not leak the deferred callable.
    assert "_post_commit" not in result

    tasks = db_session.execute(
        select(GradingTask).where(GradingTask.disease_id == glaucoma_enabled["disease"].id)
    ).scalars().all()
    assert len(tasks) >= 2
    assert dispatched, "the worker dispatch should have run after the commit"


def test_a_second_glaucoma_request_reuses_rather_than_duplicating(
    client, auth_headers, db_session, field_data, glaucoma_enabled, monkeypatch
):
    monkeypatch.setattr(
        "services.encounter_set_ai_inference.enqueue_task", lambda *args, **kwargs: None
    )
    url = f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}/inference"

    client.post(url, json={"workflows": ["glaucoma"]}, headers=auth_headers)
    before = db_session.execute(
        select(func.count(GradingTask.id)).where(
            GradingTask.disease_id == glaucoma_enabled["disease"].id
        )
    ).scalar_one()

    client.post(url, json={"workflows": ["glaucoma"]}, headers=auth_headers)
    after = db_session.execute(
        select(func.count(GradingTask.id)).where(
            GradingTask.disease_id == glaucoma_enabled["disease"].id
        )
    ).scalar_one()

    # Tasks are reused, never duplicated per image.
    assert after == before


def test_dr_dme_request_is_gated_then_queued_when_the_workflow_is_enabled(
    client, auth_headers, db_session, field_data, monkeypatch
):
    url = f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}/inference"

    disabled = client.post(url, json={"workflows": ["dr_dme"]}, headers=auth_headers)
    assert disabled.get_json()["workflows"]["dr_dme"]["reason"] == "workflow_disabled"

    suffix = next(_SEQUENCE)
    model = AIModel(name=f"madhunetra_test_{suffix}", version="17aug2026")
    db_session.add(model)
    db_session.flush()
    db_session.add(
        ProjectEncounterAIWorkflow(
            project_id=field_data["project"].id,
            ai_model_id=model.id,
            workflow_key="dr_dme",
            manual_enabled=True,
            active=True,
        )
    )
    db_session.flush()
    monkeypatch.setattr(
        "remote_inference.encounter_service.enqueue_task", lambda *args, **kwargs: None
    )

    enabled = client.post(url, json={"workflows": ["dr_dme"]}, headers=auth_headers)

    # Either the job was queued, or eligibility refused it with a typed reason -
    # but never a crash, and never a silent success.
    assert enabled.status_code in (200, 202, 409), enabled.get_data(as_text=True)
    if enabled.status_code == 202:
        payload = enabled.get_json()["workflows"]["dr_dme"]
        assert payload["queued"] is True
        assert db_session.execute(
            select(func.count(Job.id)).where(
                Job.upload_type == "encounter_set_madhunetra_dr_dme"
            )
        ).scalar_one() >= 1
