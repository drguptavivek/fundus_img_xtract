from celery_tasks.tasks import iitk_tasks


def test_config_sync_returns_partial_result_without_repeating_project_scan(monkeypatch):
    monkeypatch.setattr(iitk_tasks, "sync_config", lambda config_id, full=False: {"config_id": config_id, "failed": 1})

    assert iitk_tasks.run_iitk_config_sync_task.run(7, False)["failed"] == 1


def test_config_sync_returns_success_without_retry(monkeypatch):
    monkeypatch.setattr(iitk_tasks, "sync_config", lambda config_id, full=False: {"config_id": config_id, "failed": 0})

    assert iitk_tasks.run_iitk_config_sync_task.run(7, False)["config_id"] == 7


def test_stale_sync_recovery_task_delegates_without_retry(monkeypatch):
    monkeypatch.setattr(
        iitk_tasks,
        "recover_stale_config_syncs",
        lambda: {"reclaimed_config_ids": [7], "count": 1},
    )

    assert iitk_tasks.recover_stale_iitk_syncs_task.run()["reclaimed_config_ids"] == [7]
