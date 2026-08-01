from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from models import AIModel, AIModelDisease, AIModelIntegration, Project
from remote_inference import automated_service
from remote_inference.models import ProjectAutomatedRemoteInferenceRule
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileDisease, UploadProfileKind


def _configured_project(db_session, disease):
    project = Project(title=f"Automated Project {uuid4()}", code=f"AUTO{str(uuid4())[:8]}", active=True)
    profile = UploadProfile(name=f"Direct Glaucoma {uuid4()}", active=True, allow_mydriatic=True, allow_non_mydriatic=True)
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind="direct_image"))
    model = AIModel(name=f"Wadhwani {uuid4()}", version="test")
    model.integration = AIModelIntegration(provider=WADHWANI_PROVIDER, is_enabled=True, client_id="client", bearer_token="token")
    model.disease_links.append(AIModelDisease(disease_id=disease.id, active=True))
    db_session.add_all([project, profile, model])
    db_session.flush()
    db_session.add(ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True))
    db_session.flush()
    return project, profile, model


def _use_test_session(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(automated_service, "transaction_scope", use_test_session)


def test_project_options_are_derived_from_active_profile_capabilities(db_session, core_test_data):
    project, profile, model = _configured_project(db_session, core_test_data["glaucoma"])

    context = automated_service.project_automated_workflow_context(db_session, project.id)

    option = next(row for row in context["automated_remote_inference_workflows"] if row.ai_model_id == model.id)
    assert option.upload_kind == "direct_image"
    assert option.supporting_profiles == (profile.name,)
    assert option.enabled is False


def test_save_project_rules_creates_and_deactivates_project_owned_rows(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(automated_service, "manager_lab_unit_ids", lambda _user_id: {core_test_data["lab_unit"].id})
    project, _profile, model = _configured_project(db_session, core_test_data["glaucoma"])
    selected = [automated_service.AutomatedRemoteInferenceRuleInput(
        disease_id=core_test_data["glaucoma"].id,
        ai_model_id=model.id,
        upload_kind="direct_image",
    )]

    result = automated_service.set_project_automated_rules(1, project.id, selected)
    assert result.success is True
    rule = db_session.query(ProjectAutomatedRemoteInferenceRule).filter_by(project_id=project.id).one()
    assert rule.active is True

    cleared = automated_service.set_project_automated_rules(1, project.id, [])
    assert cleared.success is True
    db_session.refresh(rule)
    assert rule.active is False


def test_save_rejects_upload_path_not_supported_by_project_profiles(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(automated_service, "manager_lab_unit_ids", lambda _user_id: {core_test_data["lab_unit"].id})
    project, _profile, model = _configured_project(db_session, core_test_data["glaucoma"])

    result = automated_service.set_project_automated_rules(1, project.id, [
        automated_service.AutomatedRemoteInferenceRuleInput(
            disease_id=core_test_data["glaucoma"].id,
            ai_model_id=model.id,
            upload_kind="remidio",
        )
    ])

    assert result.success is False
    assert "not supported" in result.message
