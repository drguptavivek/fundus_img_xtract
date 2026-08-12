from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

from celery_tasks.tasks import wadhwani_tasks


def test_wadhwani_batch_processes_at_most_three_items_concurrently(monkeypatch):
    lock = threading.Lock()
    active = 0
    maximum_active = 0
    item_states: list[tuple[str, str, str]] = []
    job_states: list[tuple[str, str, str | None]] = []

    def _run_task_inference(**kwargs):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return SimpleNamespace(
            status="success",
            message="done",
            grade_id=kwargs["task_id"] + 100,
            inference_run_id=kwargs["task_id"] + 200,
            error_code=None,
        )

    monkeypatch.setattr(wadhwani_tasks, "run_task_inference", _run_task_inference)
    monkeypatch.setattr(
        wadhwani_tasks,
        "db_set_item_state",
        lambda token, item, state, detail=None: item_states.append((item, state, detail)),
    )
    monkeypatch.setattr(
        wadhwani_tasks,
        "db_set_job_status",
        lambda token, state, error=None: job_states.append((token, state, error)),
    )
    monkeypatch.setattr(wadhwani_tasks, "refresh_ai_inference_runs_materialized_view", lambda: True)

    wadhwani_tasks.run_wadhwani_glaucoma_batch_task.run("job-token", list(range(1, 8)), user_id=9)

    assert maximum_active == 3
    assert job_states == [("job-token", "processing", None), ("job-token", "done", None)]
    assert sum(1 for _, state, _ in item_states if state == "processing") == 7
    assert sum(1 for _, state, _ in item_states if state == "ok") == 7


def test_wadhwani_batch_contains_unexpected_item_failure(monkeypatch):
    item_states: list[tuple[str, str, str | None]] = []
    job_states: list[tuple[str, str, str | None]] = []

    def _run_task_inference(*, task_id, **kwargs):
        if task_id == 2:
            raise RuntimeError("presigned-url-must-not-escape")
        return SimpleNamespace(
            status="success",
            message="done",
            grade_id=task_id + 100,
            inference_run_id=task_id + 200,
            error_code=None,
        )

    monkeypatch.setattr(wadhwani_tasks, "run_task_inference", _run_task_inference)
    monkeypatch.setattr(
        wadhwani_tasks,
        "db_set_item_state",
        lambda token, item, state, detail=None: item_states.append((item, state, detail)),
    )
    monkeypatch.setattr(
        wadhwani_tasks,
        "db_set_job_status",
        lambda token, state, error=None: job_states.append((token, state, error)),
    )
    monkeypatch.setattr(wadhwani_tasks, "refresh_ai_inference_runs_materialized_view", lambda: True)

    wadhwani_tasks.run_wadhwani_glaucoma_batch_task.run("job-token", [1, 2, 3], user_id=9)

    error_detail = next(json.loads(detail) for item, state, detail in item_states if state == "error")
    assert error_detail["error_code"] == "unexpected_worker_error"
    assert "presigned-url" not in error_detail["message"]
    assert job_states[-1] == ("job-token", "partial", None)
