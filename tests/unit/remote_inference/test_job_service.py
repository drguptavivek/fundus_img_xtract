from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from auth.utils import utcnow
from models import AIInferenceRun, AIModel, DirectImageUpload, GradingTask, Job, JobItem, User
from remote_inference import job_service


def test_processing_job_becomes_resumable_only_after_processing_item_is_stale():
    now = utcnow()
    job = SimpleNamespace(
        upload_type=job_service.WADHWANI_ENCOUNTER_SET_JOB_TYPE,
        status="processing",
        updated_at=now - timedelta(minutes=10),
    )
    active_item = SimpleNamespace(state="processing", started_at=now - timedelta(minutes=1))
    stale_item = SimpleNamespace(state="processing", started_at=now - timedelta(minutes=10))

    assert job_service.is_job_resumable(job, [active_item], now=now) is False
    assert job_service.is_job_resumable(job, [stale_item], now=now) is True


def test_resume_interrupted_job_preserves_completed_items_and_requeues_unfinished(
    db_session,
    core_test_data,
    app,
    monkeypatch,
):
    admin_user = db_session.query(User).filter_by(username="test_admin").one()
    lab = core_test_data["lab_unit"]
    glaucoma = core_test_data["glaucoma"]
    model = AIModel(name=f"resume-wadhwani-{uuid4().hex[:8]}", version="1")
    db_session.add(model)
    db_session.flush()

    tasks = []
    for index in range(2):
        image = DirectImageUpload(
            uuid=str(uuid4()),
            original_filename=f"resume-{index}.jpg",
            filename=f"resume-{index}.jpg",
            folder_rel=f"resume-test-{uuid4().hex[:8]}",
            file_hash=uuid4().hex,
            uploader_id=admin_user.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
            camera_id=core_test_data["camera"].id,
            disease_id=glaucoma.id,
            area_id=1,
        )
        db_session.add(image)
        db_session.flush()
        task = GradingTask(
            direct_image_upload_id=image.id,
            disease_id=glaucoma.id,
            lab_unit_id=lab.id,
        )
        db_session.add(task)
        db_session.flush()
        tasks.append(task)

    job = Job(
        token=uuid4().hex,
        status="processing",
        upload_type=job_service.WADHWANI_ENCOUNTER_SET_JOB_TYPE,
        upload_kind="encounter_set",
        uploader_user_id=admin_user.id,
        updated_at=utcnow() - timedelta(minutes=10),
    )
    db_session.add(job)
    db_session.flush()
    completed_item = JobItem(job_id=job.id, filename=f"task:{tasks[0].id}", state="ok")
    interrupted_item = JobItem(
        job_id=job.id,
        filename=f"task:{tasks[1].id}",
        state="processing",
        started_at=utcnow() - timedelta(minutes=10),
    )
    abandoned_run = AIInferenceRun(
        task_id=tasks[1].id,
        ai_model_id=model.id,
        status="running",
        source="internal",
        started_at=utcnow() - timedelta(minutes=10),
    )
    db_session.add_all([completed_item, interrupted_item, abandoned_run])
    db_session.flush()

    queued = {}
    monkeypatch.setattr(
        job_service,
        "enqueue_task",
        lambda task_name, token, task_ids, **kwargs: queued.update(
            task_name=task_name, token=token, task_ids=task_ids, kwargs=kwargs
        ),
    )

    result = job_service.resume_interrupted_wadhwani_job(job_token=job.token, user_id=admin_user.id)

    assert result.success is True
    assert result.payload["resumed_task_count"] == 1
    assert queued["task_ids"] == [tasks[1].id]
    assert completed_item.state == "ok"
    assert interrupted_item.state == "queued"
    assert abandoned_run.status == "failed"
    assert abandoned_run.error_code == "worker_interrupted"
    assert job.status == "queued"
