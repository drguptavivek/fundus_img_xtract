from utils.celery_queue_config import infer_celery_queue


def test_wadhwani_tasks_use_dedicated_queue():
    assert infer_celery_queue("celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task") == "wadhwani"


def test_remidio_tasks_remain_on_maintenance_queue():
    assert infer_celery_queue("celery_tasks.tasks.remidio_tasks.run_remidio_api_project_sync_task") == "maintenance"


def test_pii_detection_tasks_are_rate_limited_and_others_are_not(monkeypatch):
    monkeypatch.setenv("PII_DETECTION_RATE_LIMIT", "24/m")
    import celery_app

    app = celery_app.make_celery_app()
    (throttle,) = app.conf.task_annotations
    pii = type("T", (), {"name": "celery_tasks.tasks.encounter_set_tasks.process_encounter_set_image_data_combined_task"})
    other = type("T", (), {"name": "celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task"})
    assert throttle.annotate(pii) == {"rate_limit": "24/m"}
    assert throttle.annotate(other) is None

    monkeypatch.setenv("PII_DETECTION_RATE_LIMIT", "")
    assert not celery_app.make_celery_app().conf.task_annotations
