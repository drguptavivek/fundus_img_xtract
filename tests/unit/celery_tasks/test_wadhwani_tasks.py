from __future__ import annotations

import json
import logging
import threading
import time
from types import SimpleNamespace

from celery_tasks.tasks import wadhwani_tasks


def test_madhunetra_failure_is_written_to_sanitized_wai_log(monkeypatch, caplog):
    class ProviderError(RuntimeError):
        step = "submit"
        code = "model_unavailable"
        status_code = 502
        retryable = True

    def _fail_inference(**kwargs):
        raise ProviderError("failed URL https://storage.example/file?token=secret")

    item_states: list[tuple[str, str, str | None]] = []
    monkeypatch.setattr(wadhwani_tasks, "run_encounter_inference", _fail_inference)
    monkeypatch.setattr(
        wadhwani_tasks,
        "db_set_item_state",
        lambda token, item, state, detail=None: item_states.append((item, state, detail)),
    )
    monkeypatch.setattr(wadhwani_tasks, "db_set_job_status", lambda *args, **kwargs: None)
    caplog.set_level(logging.ERROR, logger="wai")

    wadhwani_tasks.run_madhunetra_dr_dme_batch_task.run(
        "job-token", [42], user_id=9
    )

    assert "provider_failure provider=madhunetrai workflow=dr_dme" in caplog.text
    assert "job=job-token encounter_id=42 stage=submit" in caplog.text
    assert "error_code=model_unavailable http_status=502 retryable=True" in caplog.text
    assert "token=secret" not in caplog.text
    assert "token=***" in caplog.text
    error_detail = next(
        json.loads(detail) for _, state, detail in item_states if state == "error"
    )
    assert "token=secret" not in error_detail["detail"]


def test_wadhwani_batch_processes_at_most_two_items_concurrently(monkeypatch):
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

    assert maximum_active == 2
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
    sleeps: list[int] = []
    monkeypatch.setattr(wadhwani_tasks.time, "sleep", lambda seconds: sleeps.append(seconds))

    wadhwani_tasks.run_wadhwani_glaucoma_batch_task.run("job-token", [1, 2, 3], user_id=9)

    error_detail = next(json.loads(detail) for item, state, detail in item_states if state == "error")
    assert error_detail["error_code"] == "unexpected_worker_error"
    assert "presigned-url" not in error_detail["message"]
    assert sleeps == [5, 5]
    assert sum(1 for item, state, _ in item_states if item == "task:2" and state == "error") == 3
    assert job_states[-1] == ("job-token", "partial", None)


def test_wadhwani_batch_stops_retry_passes_after_item_recovers(monkeypatch):
    attempts: dict[int, int] = {}
    item_states: list[tuple[str, str, str | None]] = []
    job_states: list[tuple[str, str, str | None]] = []
    sleeps: list[int] = []

    def _run_task_inference(*, task_id, **kwargs):
        attempts[task_id] = attempts.get(task_id, 0) + 1
        failed = task_id == 2 and attempts[task_id] == 1
        return SimpleNamespace(
            status="failed" if failed else "success",
            message="503" if failed else "done",
            grade_id=None if failed else task_id + 100,
            inference_run_id=task_id + 200,
            error_code="initialize_failed" if failed else None,
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
    monkeypatch.setattr(wadhwani_tasks.time, "sleep", lambda seconds: sleeps.append(seconds))

    wadhwani_tasks.run_wadhwani_glaucoma_batch_task.run("job-token", [1, 2, 3], user_id=9)

    assert attempts == {1: 1, 2: 2, 3: 1}
    assert sleeps == [5]
    assert sum(1 for item, state, _ in item_states if item == "task:2" and state == "processing") == 2
    assert job_states[-1] == ("job-token", "done", None)


def test_wadhwani_retry_passes_are_serial_with_two_second_item_gap(monkeypatch):
    active = 0
    maximum_retry_active = 0
    lock = threading.Lock()
    attempts: dict[int, int] = {}
    sleeps: list[int] = []

    def _run_task_inference(*, task_id, **kwargs):
        nonlocal active, maximum_retry_active
        attempts[task_id] = attempts.get(task_id, 0) + 1
        if attempts[task_id] > 1:
            with lock:
                active += 1
                maximum_retry_active = max(maximum_retry_active, active)
            with lock:
                active -= 1
        return SimpleNamespace(
            status="failed",
            message="503",
            grade_id=None,
            inference_run_id=task_id + 200,
            error_code="initialize_failed",
        )

    monkeypatch.setattr(wadhwani_tasks, "run_task_inference", _run_task_inference)
    monkeypatch.setattr(wadhwani_tasks, "db_set_item_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(wadhwani_tasks, "db_set_job_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(wadhwani_tasks, "refresh_ai_inference_runs_materialized_view", lambda: True)
    monkeypatch.setattr(wadhwani_tasks.time, "sleep", lambda seconds: sleeps.append(seconds))

    wadhwani_tasks.run_wadhwani_glaucoma_batch_task.run("job-token", [1, 2], user_id=9)

    assert attempts == {1: 3, 2: 3}
    assert maximum_retry_active == 1
    assert sleeps == [5, 2, 5, 2]
