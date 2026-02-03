import json

from models import ImageMetadataBackfillJob, LabUnit
from utils.image_metadata_backfill import enqueue_system_image_metadata_backfill


def test_enqueue_system_backfill_creates_job_and_enqueues(db_session, core_test_data, monkeypatch):
    lab_unit_ids = [lu.id for lu in db_session.query(LabUnit).order_by(LabUnit.id.asc()).all()]
    assert lab_unit_ids

    enqueued = {}

    def fake_enqueue(task_name, *args, **kwargs):
        enqueued["task_name"] = task_name
        enqueued["args"] = args
        enqueued["kwargs"] = kwargs

    monkeypatch.setattr("utils.celery_helpers.celery_enabled", lambda: True)
    monkeypatch.setattr("utils.celery_helpers.enqueue_task", fake_enqueue)

    result = enqueue_system_image_metadata_backfill(requested_limit=14, run_metadata=True, run_pii=True)

    assert result is True
    job = db_session.query(ImageMetadataBackfillJob).order_by(ImageMetadataBackfillJob.id.desc()).first()
    assert job is not None
    assert job.status == "queued"
    assert job.requested_limit == 14
    assert job.run_metadata is True
    assert job.run_pii is True
    assert json.loads(job.allowed_lab_unit_ids) == lab_unit_ids
    assert enqueued["task_name"] == "celery_tasks.tasks.metadata_tasks.run_image_metadata_backfill_job_task"
    assert enqueued["args"] == (job.id,)


def test_enqueue_system_backfill_skips_when_active_job(db_session, core_test_data, monkeypatch):
    db_session.add(
        ImageMetadataBackfillJob(
            status="running",
            requested_limit=5,
            run_metadata=True,
            run_pii=True,
            created_by_username="system",
            allowed_lab_unit_ids=json.dumps([row[0] for row in db_session.query(LabUnit.id).all()]),
        )
    )
    db_session.commit()

    enqueued = {"called": False}

    def fake_enqueue(task_name, *args, **kwargs):
        enqueued["called"] = True

    monkeypatch.setattr("utils.celery_helpers.celery_enabled", lambda: True)
    monkeypatch.setattr("utils.celery_helpers.enqueue_task", fake_enqueue)

    result = enqueue_system_image_metadata_backfill(requested_limit=14, run_metadata=True, run_pii=True)

    assert result is False
    assert enqueued["called"] is False
