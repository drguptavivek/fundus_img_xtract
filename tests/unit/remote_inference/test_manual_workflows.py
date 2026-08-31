from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from models import AIModel, AIModelDisease, AIModelIntegration, PatientEncounters, Project
from remote_inference import manual_service
from remote_inference.models import ProjectManualRemoteInferenceWorkflow


def _wadhwani_model(db_session, glaucoma):
    model = AIModel(name=f"Manual Wadhwani {uuid4()}", version="test")
    model.integration = AIModelIntegration(
        provider=manual_service.WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    model.disease_links.append(AIModelDisease(disease_id=glaucoma.id, active=True))
    db_session.add(model)
    db_session.flush()
    return model


def _use_test_session(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(manual_service, "transaction_scope", use_test_session)


def test_project_manual_workflow_can_be_enabled_and_deactivated_without_deletion(
    db_session,
    core_test_data,
    monkeypatch,
):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(manual_service, "manager_lab_unit_ids", lambda _user_id: {core_test_data["lab_unit"].id})
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    model = _wadhwani_model(db_session, glaucoma)
    project = Project(title=f"Manual Wadhwani Project {uuid4()}", code=f"MW{uuid4().hex[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    key = manual_service.ManualRemoteInferenceWorkflowKey(
        disease_id=glaucoma.id,
        ai_model_id=model.id,
        upload_kind="encounter_set",
    )

    enabled = manual_service.set_project_manual_workflows(1, project.id, [key])

    assert enabled.success is True
    mapping = db_session.query(ProjectManualRemoteInferenceWorkflow).filter_by(project_id=project.id).one()
    assert mapping.active is True
    assert manual_service.project_allows_manual_wadhwani(db_session, project.id) is True
    project.active = False
    db_session.flush()
    assert manual_service.project_allows_manual_wadhwani(db_session, project.id) is False
    project.active = True
    db_session.flush()

    disabled = manual_service.set_project_manual_workflows(1, project.id, [])

    assert disabled.success is True
    db_session.refresh(mapping)
    assert mapping.active is False
    assert manual_service.project_allows_manual_wadhwani(db_session, project.id) is False


def test_manual_wadhwani_project_listing_uses_project_mapping_not_upload_profile(
    db_session,
    core_test_data,
    monkeypatch,
):
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    model = _wadhwani_model(db_session, glaucoma)
    project = Project(title=f"Mapped Manual Project {uuid4()}", code=f"MMP{uuid4().hex[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    db_session.add(
        ProjectManualRemoteInferenceWorkflow(
            project_id=project.id,
            disease_id=glaucoma.id,
            ai_model_id=model.id,
            upload_kind="encounter_set",
            active=True,
        )
    )
    db_session.add(
        PatientEncounters(
            name=f"Manual inference encounter {uuid4()}",
            patient_id=f"manual-{uuid4()}",
            capture_date="2026-08-01",
            capture_date_dt=date(2026, 8, 1),
            is_set_based=True,
            project_id=project.id,
            lab_unit_id=lab_unit.id,
        )
    )
    db_session.flush()
    monkeypatch.setattr("authz.project_access.can_run_wai", lambda *args, **kwargs: True)

    projects = manual_service.list_manual_wadhwani_projects(db_session, object())

    assert {row["id"] for row in projects} == {project.id}


def test_project_manual_workflow_context_reports_enabled_wadhwani_option(db_session, core_test_data):
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    model = _wadhwani_model(db_session, glaucoma)
    project = Project(title=f"Manual Context Project {uuid4()}", code=f"MCP{uuid4().hex[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    db_session.add(
        ProjectManualRemoteInferenceWorkflow(
            project_id=project.id,
            disease_id=glaucoma.id,
            ai_model_id=model.id,
            upload_kind="encounter_set",
            active=True,
        )
    )
    db_session.flush()

    context = manual_service.project_manual_workflow_context(db_session, project.id)

    selected = [row for row in context["manual_remote_inference_workflows"] if row.ai_model_id == model.id]
    assert len(selected) == 1
    assert selected[0].enabled is True
    assert context["manual_remote_inference_enabled"] is True


def test_manual_workflow_parser_ignores_malformed_values():
    parsed = manual_service.workflow_keys_from_values(["1:2:encounter_set", "bad", "0:2:encounter_set"])

    assert parsed == [
        manual_service.ManualRemoteInferenceWorkflowKey(
            disease_id=1,
            ai_model_id=2,
            upload_kind="encounter_set",
        )
    ]
