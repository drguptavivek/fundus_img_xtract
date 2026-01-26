# Celery Integration & Usage Guide

This document explains how to integrate Celery into application workflows and how to use it safely.

## When to Use Celery

Use Celery for:
- CPU-heavy or high-volume work (OCR, PII, thumbnails, metadata)
- Background migrations (local -> S3)
- Long-running exports or batch jobs

Do not use Celery for:
- Small synchronous validations
- Request/response logic that must be immediate

## Integration Principles

- **Local-first safety**: persist uploads locally first, then enqueue background work.
- **Idempotency**: tasks must be safe to retry.
- **Auditability**: record task state changes with user_id + hospital_id.
- **Isolation**: hospital-scoped tasks must never cross hospitals.

## Enqueue Helpers

Prefer helper utilities rather than calling Celery directly in routes.

Common helpers:
- `utils/celery_helpers.py`
- `utils/thumbnail_jobs.py`
- `utils/pii_detection_queue.py`
- `worker.py` (ZIP jobs)

All enqueue calls should pass `user_id` and `hospital_id` where available.

## Task Signatures

Every task must accept (and log) the following kwargs:
- `user_id`
- `hospital_id`

Example signature:

```python
@shared_task(bind=True)
def process_thumbnail_job_task(self, job_id: str, user_id: int | None = None, hospital_id: int | None = None):
    ...
```

## Queue Selection

Queue routing is defined in `celery_app.py`. When adding a new task:
1. Add the task module under `celery_tasks/tasks/`.
2. Add a routing entry in `celery_app.py` if needed.
3. Pick the correct queue for workload profile.

## Scheduling

Use DB-backed schedules (table: `celery_beat_schedules`). Create or update schedules via:

```
/admin/celery-schedules
```

Schedules are global; set `hospital_id` if needed to scope task kwargs.

### Creating a Schedule (Admin UI)

1) Open `/admin/celery-schedules`
2) Create a schedule:
   - **Name**: unique identifier
   - **Task name**: full import path (e.g., `celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task`)
   - **Schedule type**:
     - `interval`: set `interval_seconds`
     - `crontab`: set minute/hour/day fields (use `*` for any)
   - **Queue**: optional, overrides default routing
   - **Hospital/User**: optional scoping for task kwargs
3) Save; Beat picks changes within `CELERY_BEAT_DB_REFRESH_SECONDS` (default 60s)

### Notes

- Beat reads schedules from the DB on a refresh interval; restart is not required.
- Keep schedule names stable; updates are by name.
- If a schedule is disabled, Beat skips it (record remains in DB).

## Worker Separation

The system uses two worker services:
- `celery-ocr-worker` (CPU heavy)
- `celery-general-worker` (general tasks)

Keep OCR and heavy compute off the general queue.

## Adding a New Task (Step-by-Step)

1) **Create the task module**
- Add a module under `celery_tasks/tasks/` (or add to an existing file).
- Do **not** import Flask app or blueprints.

2) **Define the task**
- Include `user_id` and `hospital_id` kwargs.
- Add idempotency checks before work begins.
- Log/audit task state transitions.

Example:

```python
from celery import shared_task

@shared_task(bind=True)
def my_task(self, record_id: int, user_id: int | None = None, hospital_id: int | None = None):
    # idempotency check here
    # do work
    return {"status": "ok"}
```

3) **Select a queue**
- Choose a queue based on workload profile.
- Update routing in `celery_app.py` if needed:

```python
app.conf.update(
    task_routes={
        "celery_tasks.tasks.my_task_module.*": {"queue": "metadata"},
    }
)
```

4) **Enqueue from the app**
- Use helpers where possible.
- Always pass `user_id` and `hospital_id`.

```python
from utils.celery_helpers import enqueue_task

enqueue_task(
    "celery_tasks.tasks.my_task_module.my_task",
    args=[record_id],
    kwargs={"user_id": current_user.id, "hospital_id": hospital_id},
    queue="metadata",
)
```

5) **Poll status (if needed)**
- If you need status, store `task_id` and query Celery:

```python
from celery.result import AsyncResult
from celery_app import celery_app

result = AsyncResult(task_id, app=celery_app)
state = result.state
```

6) **Document the use case**
- Add the task to `docs/10-DEVELOP/celery-use-cases.md` with queue, trigger, and retry notes.

## Common Pitfalls

- Forgetting `user_id`/`hospital_id` in kwargs (audit scope loss)
- Enqueuing before local persistence completes
- Long-running tasks on the general queue (starves UI)
- Using Celery for tasks that need immediate UI feedback

## Logging and Audit

- Use a dedicated logger for each task domain (e.g., `celery.pii`, `celery.thumbnails`).
- Sanitize any user-provided input in logs using `sanitize_log_value`.
- Record task lifecycle events (queued, started, completed, failed) in audit logs.
- Include `user_id` and `hospital_id` in log context where possible.

Example:

```python
import logging
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("celery.thumbnails")
logger.info(
    "thumbnail task started: job_id=%s user_id=%s hospital_id=%s",
    sanitize_log_value(job_id),
    sanitize_log_value(user_id),
    sanitize_log_value(hospital_id),
)
```

## Handling Failures and Restarts

### Checking failures

- Review worker logs:
  ```
  $DC logs -f celery-ocr-worker
  $DC logs -f celery-general-worker
  ```
- Inspect the app’s job tables (PII, metadata backfills, exports, thumbnails) for failed status.
- Use admin dashboards where available (e.g., thumbnail maintenance).

### Restarting workers

Use Docker to restart the worker services:

```
$DC restart celery-ocr-worker celery-general-worker
```

### Retrying / re-queuing

- If tasks are idempotent, you can re-enqueue safely.
- Use existing admin actions where available (e.g., “run PII queue”, “backfill metadata”).
- For S3 migrations, prefer per-hospital manual triggers.

### Deleting failed records

Do **not** delete job records unless you are certain they are unrecoverable:
- Job records provide audit and traceability.
- For retries, mark status as queued or create a new job entry instead of deleting.

## Example: Enqueue Pattern

```python
from utils.celery_helpers import enqueue_task

enqueue_task(
    "celery_tasks.tasks.thumbnail_tasks.process_thumbnail_job_task",
    args=[job_id],
    kwargs={"user_id": current_user.id, "hospital_id": hospital_id},
    queue="thumbnails",
)
```
