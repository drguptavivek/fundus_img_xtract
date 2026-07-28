from utils.celery_queue_config import infer_celery_queue


def test_wadhwani_tasks_use_dedicated_queue():
    assert infer_celery_queue("celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task") == "wadhwani"


def test_remidio_tasks_remain_on_maintenance_queue():
    assert infer_celery_queue("celery_tasks.tasks.remidio_tasks.run_remidio_api_project_sync_task") == "maintenance"
