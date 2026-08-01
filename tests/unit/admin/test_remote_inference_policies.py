from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from models import AIModel, AIModelDisease, AIModelIntegration, Project
from remote_inference import admin_service
from remote_inference.models import ProjectRemoteInferencePolicy, RemoteInferencePolicy, RemoteInferencePolicyRule
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER


def _remote_model(db_session, disease):
    ai_model = AIModel(name=f"Remote Admin Model {uuid4()}", version="test")
    ai_model.integration = AIModelIntegration(
        provider=WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    ai_model.disease_links.append(AIModelDisease(disease_id=disease.id, active=True))
    db_session.add(ai_model)
    db_session.flush()
    return ai_model


def _use_test_session(db_session, monkeypatch):
    @contextmanager
    def use_test_session():
        yield db_session
        db_session.flush()

    monkeypatch.setattr(admin_service, "transaction_scope", use_test_session)


def _policy_input(disease_id: int, ai_model_id: int, *, upload_kind: str = "encounter_set"):
    return admin_service.RemoteInferencePolicyInput(
        name=f"Reusable Policy {uuid4()}",
        description="Reusable remote inference policy",
        rules=[
            admin_service.RemoteInferenceRuleInput(
                disease_id=disease_id,
                ai_model_id=ai_model_id,
                upload_kind=upload_kind,
                trigger_timing="on_image_received",
                encounter_eligibility="always",
                image_selection="disc_or_macula_images",
            )
        ],
    )


def test_save_policy_creates_reusable_policy_without_project_assignment(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {core_test_data["lab_unit"].id})
    ai_model = _remote_model(db_session, core_test_data["glaucoma"])

    result = admin_service.save_policy(
        manager_user_id=1,
        policy_id=None,
        policy_input=_policy_input(core_test_data["glaucoma"].id, ai_model.id),
    )

    assert result.success is True
    policy = db_session.get(RemoteInferencePolicy, result.payload["remote_inference_policy_id"])
    assert policy.name.startswith("Reusable Policy")
    assert len(policy.rules) == 1
    assert db_session.query(ProjectRemoteInferencePolicy).filter_by(remote_inference_policy_id=policy.id).count() == 0


def test_save_policy_reconciles_existing_rules_without_duplicate_keys(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {core_test_data["lab_unit"].id})
    ai_model = _remote_model(db_session, core_test_data["glaucoma"])
    policy = RemoteInferencePolicy(name=f"Editable Policy {uuid4()}", active=True)
    existing_rule = RemoteInferencePolicyRule(
        disease_id=core_test_data["glaucoma"].id,
        ai_model_id=ai_model.id,
        upload_kind="encounter_set",
        trigger_timing="after_verification",
        encounter_eligibility="always",
        image_selection="disc_focused_images",
        active=True,
    )
    policy.rules.append(existing_rule)
    db_session.add(policy)
    db_session.flush()
    existing_rule_id = existing_rule.id

    policy_input = admin_service.RemoteInferencePolicyInput(
        name=policy.name,
        description="Updated policy",
        rules=[
            admin_service.RemoteInferenceRuleInput(
                disease_id=core_test_data["glaucoma"].id,
                ai_model_id=ai_model.id,
                upload_kind=upload_kind,
                trigger_timing="on_image_received",
                encounter_eligibility="always",
                image_selection="all_eligible_images",
            )
            for upload_kind in ("encounter_set", "direct_image", "remidio")
        ],
    )

    result = admin_service.save_policy(1, policy.id, policy_input)

    assert result.success is True
    db_session.refresh(policy)
    rules = sorted(policy.rules, key=lambda rule: rule.display_order)
    assert len(rules) == 3
    assert rules[0].id == existing_rule_id
    assert rules[0].trigger_timing == "on_image_received"
    assert [rule.upload_kind for rule in rules] == ["encounter_set", "direct_image", "remidio"]
    assert all(rule.active for rule in rules)


def test_save_policy_deactivates_removed_rules(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {core_test_data["lab_unit"].id})
    ai_model = _remote_model(db_session, core_test_data["glaucoma"])
    policy = RemoteInferencePolicy(name=f"Policy With Removed Rule {uuid4()}", active=True)
    removed_rule = RemoteInferencePolicyRule(
        disease_id=core_test_data["glaucoma"].id,
        ai_model_id=ai_model.id,
        upload_kind="direct_image",
        trigger_timing="on_image_received",
        encounter_eligibility="always",
        image_selection="all_eligible_images",
        active=True,
    )
    policy.rules.append(removed_rule)
    db_session.add(policy)
    db_session.flush()

    result = admin_service.save_policy(
        1,
        policy.id,
        admin_service.RemoteInferencePolicyInput(name=policy.name, description=None, rules=[]),
    )

    assert result.success is True
    db_session.refresh(removed_rule)
    assert removed_rule.active is False


def test_assign_project_policy_reuses_existing_policy_and_can_clear_assignment(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {core_test_data["lab_unit"].id})
    ai_model = _remote_model(db_session, core_test_data["glaucoma"])
    policy = RemoteInferencePolicy(name=f"Reusable Assigned Policy {uuid4()}", active=True)
    policy.rules.append(
        RemoteInferencePolicyRule(
            disease_id=core_test_data["glaucoma"].id,
            ai_model_id=ai_model.id,
            upload_kind="encounter_set",
            trigger_timing="after_verification",
            encounter_eligibility="always",
            image_selection="disc_focused_images",
            active=True,
        )
    )
    project = Project(title=f"Remote Project {uuid4()}", code=f"RP{str(uuid4())[:8]}", active=True)
    db_session.add_all([policy, project])
    db_session.flush()

    assigned = admin_service.assign_project_policy(1, project.id, policy.id)

    assert assigned.success is True
    assignment = db_session.query(ProjectRemoteInferencePolicy).filter_by(project_id=project.id).one()
    assert assignment.remote_inference_policy_id == policy.id
    assert assignment.active is True

    cleared = admin_service.assign_project_policy(1, project.id, None)

    assert cleared.success is True
    db_session.refresh(assignment)
    assert assignment.active is False


def test_deactivating_policy_deactivates_project_assignment(db_session, core_test_data, monkeypatch):
    _use_test_session(db_session, monkeypatch)
    monkeypatch.setattr(admin_service, "manager_lab_unit_ids", lambda manager_user_id: {core_test_data["lab_unit"].id})
    ai_model = _remote_model(db_session, core_test_data["glaucoma"])
    policy = RemoteInferencePolicy(name=f"Policy To Deactivate {uuid4()}", active=True)
    policy.rules.append(
        RemoteInferencePolicyRule(
            disease_id=core_test_data["glaucoma"].id,
            ai_model_id=ai_model.id,
            upload_kind="encounter_set",
            trigger_timing="on_image_received",
            encounter_eligibility="always",
            image_selection="all_eligible_images",
            active=True,
        )
    )
    project = Project(title=f"Remote Project {uuid4()}", code=f"RPD{str(uuid4())[:8]}", active=True)
    db_session.add_all([policy, project])
    db_session.flush()
    assignment = ProjectRemoteInferencePolicy(project_id=project.id, remote_inference_policy_id=policy.id, active=True)
    db_session.add(assignment)
    db_session.flush()

    result = admin_service.set_policy_active(1, policy.id, False)

    assert result.success is True
    db_session.refresh(policy)
    db_session.refresh(assignment)
    assert policy.active is False
    assert assignment.active is False
