from celery_tasks.tasks import iitk_tasks


def test_config_sync_returns_partial_result_without_repeating_project_scan(monkeypatch):
    monkeypatch.setattr(iitk_tasks, "sync_config", lambda config_id, full=False: {"config_id": config_id, "failed": 1})

    assert iitk_tasks.run_iitk_config_sync_task.run(7, False)["failed"] == 1


def test_config_sync_returns_success_without_retry(monkeypatch):
    monkeypatch.setattr(iitk_tasks, "sync_config", lambda config_id, full=False: {"config_id": config_id, "failed": 0})

    assert iitk_tasks.run_iitk_config_sync_task.run(7, False)["config_id"] == 7
