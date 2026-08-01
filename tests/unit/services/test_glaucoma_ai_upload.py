from werkzeug.datastructures import FileStorage
from types import SimpleNamespace

from models import AIModel, AIModelIntegration, Disease, Project
from remote_inference.models import ProjectAutomatedRemoteInferenceRule
from services.glaucoma_ai_upload import (
    GlaucomaAIUploadItem,
    GlaucomaAIUploadSelection,
    MAX_GLAUCOMA_AI_UPLOAD_FILES,
    _enqueue_wadhwani_inference,
    _validate_glaucoma_ai_workflow,
    process_glaucoma_ai_uploads,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UploadProfileError


def _selection() -> GlaucomaAIUploadSelection:
    return GlaucomaAIUploadSelection(project_id=1, lab_unit_id=1, camera_id=1, area_id=1)


def test_glaucoma_ai_upload_rejects_missing_files():
    result = process_glaucoma_ai_uploads(
        files=[],
        user_id=1,
        username="uploader",
        remote_addr="127.0.0.1",
        selection=_selection(),
    )

    assert result.success_count == 0
    assert result.error_count == 1
    assert result.items[0].message == "No files selected."


def test_glaucoma_ai_upload_rejects_more_than_ten_files():
    files = [FileStorage(filename=f"image-{idx}.jpg") for idx in range(MAX_GLAUCOMA_AI_UPLOAD_FILES + 1)]

    result = process_glaucoma_ai_uploads(
        files=files,
        user_id=1,
        username="uploader",
        remote_addr="127.0.0.1",
        selection=_selection(),
    )

    assert result.success_count == 0
    assert result.error_count == 1
    assert "Upload at most 10 images" in result.items[0].message


def test_glaucoma_ai_upload_enqueue_uses_existing_wadhwani_batch_task(monkeypatch):
    captured = {}

    def fake_create_job(filenames, rejected, **kwargs):
        captured["filenames"] = filenames
        captured["rejected"] = rejected
        captured["job_kwargs"] = kwargs
        return "job-token"

    def fake_enqueue(task_name, *args, **kwargs):
        captured["task_name"] = task_name
        captured["args"] = args
        captured["enqueue_kwargs"] = kwargs

    monkeypatch.setattr("services.glaucoma_ai_upload.db_create_job", fake_create_job)
    monkeypatch.setattr("services.glaucoma_ai_upload.enqueue_task", fake_enqueue)

    items = [
        GlaucomaAIUploadItem(
            filename="disc.jpg",
            status="success",
            message="created",
            upload_id=10,
            image_uuid="image-uuid",
            task_id=20,
            task_uuid="task-uuid",
        )
    ]

    queued = _enqueue_wadhwani_inference(
        items,
        user_id=1,
        username="uploader",
        remote_addr="127.0.0.1",
        lab_unit_id=2,
        project_id=3,
    )

    assert captured["filenames"] == ["task:20"]
    assert captured["job_kwargs"]["upload_type"] == "glaucoma_ai_upload_inference"
    assert captured["task_name"] == "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task"
    assert captured["args"] == ("job-token", [20])
    assert captured["enqueue_kwargs"]["user_id"] == 1
    assert queued[0].status == "queued"
    assert queued[0].job_token == "job-token"


def test_glaucoma_ai_upload_enqueue_skips_non_queueable_duplicate_tasks(monkeypatch):
    captured = {}

    def fake_create_job(filenames, rejected, **kwargs):
        captured["filenames"] = filenames
        return "job-token"

    def fake_enqueue(task_name, *args, **kwargs):
        captured["task_name"] = task_name

    monkeypatch.setattr("services.glaucoma_ai_upload.db_create_job", fake_create_job)
    monkeypatch.setattr("services.glaucoma_ai_upload.enqueue_task", fake_enqueue)

    items = [
        GlaucomaAIUploadItem(filename="new.jpg", status="success", message="created", task_id=10),
        GlaucomaAIUploadItem(filename="duplicate.jpg", status="success", message="duplicate", task_id=20),
    ]

    queued = _enqueue_wadhwani_inference(
        items,
        user_id=1,
        username="uploader",
        remote_addr="127.0.0.1",
        lab_unit_id=2,
        project_id=3,
        queueable_task_ids={10},
    )

    assert captured["filenames"] == ["task:10"]
    assert queued[0].status == "queued"
    assert queued[1].status == "success"
    assert queued[1].job_token is None


def test_glaucoma_ai_workflow_requires_selected_profile_linked_to_wadhwani(db_session):
    disease = Disease(name="Glaucoma Workflow Test")
    project = Project(title="Glaucoma Workflow Project", code="GLAU_WORKFLOW_TEST", active=True)
    integration = db_session.query(AIModelIntegration).filter_by(provider=WADHWANI_PROVIDER).one_or_none()
    if integration is None:
        model = AIModel(name="Glaucoma Screening MOHFW Wadhwani AI Model", version="1.0")
        db_session.add(model)
        db_session.flush()
        integration = AIModelIntegration(
            ai_model_id=model.id,
            provider=WADHWANI_PROVIDER,
            is_enabled=True,
            client_id="client",
            bearer_token="token",
        )
        db_session.add(integration)
    else:
        integration.is_enabled = True
    db_session.add_all([disease, project])
    db_session.flush()
    db_session.add(ProjectAutomatedRemoteInferenceRule(
        project_id=project.id,
        disease_id=disease.id,
        ai_model_id=integration.ai_model_id,
        upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
        trigger_timing="on_image_received",
        encounter_eligibility="always",
        image_selection="all_eligible_images",
        active=True,
    ))
    db_session.flush()

    profile = SimpleNamespace(project_id=project.id)

    assert _validate_glaucoma_ai_workflow(db_session, profile, disease.id) == integration.ai_model_id


def test_glaucoma_ai_workflow_rejects_profile_without_ai_workflow(db_session):
    disease = db_session.query(Disease).filter(Disease.name.ilike("glaucoma")).first()
    if disease is None:
        disease = Disease(name="Glaucoma")
        db_session.add(disease)
        db_session.flush()
    project = Project(title="Glaucoma Disabled Project", code="GLAU_DISABLED_TEST", active=True)
    db_session.add(project)
    db_session.flush()
    profile = SimpleNamespace(project_id=project.id)

    try:
        _validate_glaucoma_ai_workflow(db_session, profile, disease.id)
    except UploadProfileError as exc:
        assert exc.code == "ai_workflow_not_allowed"
    else:
        raise AssertionError("Expected UploadProfileError")
