from celery_tasks.tasks import wadhwani_tasks
from remote_inference import encounter_service, project_backfill_service
from services import encounter_set_ai_inference
from utils import celery_helpers


def test_project_wai_task_accepts_shared_enqueue_context(monkeypatch):
    sent = {}
    monkeypatch.setattr(celery_helpers.celery_app, "send_task", lambda name, args, kwargs: sent.update(name=name, args=args, kwargs=kwargs))
    celery_helpers.enqueue_task(
        "celery_tasks.tasks.wadhwani_tasks.run_project_wai_backfill_task",
        "job", 2, user_id=7, username="user", remote_addr=None,
    )
    states = []
    monkeypatch.setattr(wadhwani_tasks, "db_set_job_status", lambda *a, **k: states.append((a, k)))
    monkeypatch.setattr(wadhwani_tasks, "db_set_item_state", lambda *a, **k: None)
    monkeypatch.setattr(project_backfill_service, "project_encounter_ids", lambda project_id: [42])
    monkeypatch.setattr(encounter_service, "enqueue_automatic_encounters", lambda ids, **kw: {"madhunetra_encounters_queued": 1, "madhunetra_job_tokens": []})
    monkeypatch.setattr(encounter_set_ai_inference, "enqueue_wadhwani_for_encounter_ids", lambda ids, **kw: {"wadhwani_tasks_queued": 1, "wadhwani_job_tokens": []})

    wadhwani_tasks.run_project_wai_backfill_task.run(*sent["args"], **sent["kwargs"])

    assert sent["kwargs"]["hospital_id"] is None
    assert [args[1] for args, _ in states] == ["processing", "done"]


def test_project_wai_dispatch_failure_marks_job_and_item_error(monkeypatch):
    jobs, items = [], []
    monkeypatch.setattr(wadhwani_tasks, "db_set_job_status", lambda *a, **k: jobs.append((a, k)))
    monkeypatch.setattr(wadhwani_tasks, "db_set_item_state", lambda *a, **k: items.append(a))

    def fail(project_id):
        raise RuntimeError("dispatcher unavailable")

    monkeypatch.setattr(project_backfill_service, "project_encounter_ids", fail)
    wadhwani_tasks.run_project_wai_backfill_task.run("job", 2, hospital_id=None)
    assert jobs[-1][0] == ("job", "error")
    assert items[-1][2] == "error"
