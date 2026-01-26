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

## Recommended Architectural Patterns

To maintain consistency, safety, and UI responsiveness, the project follows two primary patterns for background work.

### 1. The Coordinator & Chain Model

This is the **preferred pattern** for all multi-step or batch operations (e.g., ZIP uploads, complex exports).

1.  **Coordinator Task**: A master task responsible for:
    *   **Validation**: Early exit if inputs are invalid.
    *   **Atomic Persistence**: Writing core DB records in a single transaction.
    *   **Fan-Out**: Triggering independent sub-tasks or chains for each entity.
2.  **Worker Chain**: A sequence of tasks for a single entity (e.g., `VisualTask` -> `DataTask`). 
    *   **Prioritization**: Chains ensure heavy processing (metadata) happens only after priority assets (thumbnails/visuals) are ready for the UI.

**Implementation Example:**
```python
# Coordinator
@celery_app.task
def process_batch_coordinator(items, job_token):
    # 1. Atomic DB Writes
    # 2. Fan-out
    for item in items:
        chain(priority_task.s(item), background_task.s(item)).apply_async()
```

### 2. Tracking Progress with Job Store

For any user-facing batch operation, use the `Job` and `JobItem` models (managed via `celery_job_store.py`).

*   **`db_add_job_items`**: Register sub-entities discovered during execution.
*   **`db_set_item_state`**: Provide granular status (e.g., "Thumbnailing...").
*   **`check_and_complete_job`**: Automatically aggregate item states to determine final Job status (`done`, `partial_error`, `error`).

---

## Dynamic Scheduling (Celery Beat)

The project uses a custom DB-backed scheduler that allows managing recurring tasks without code changes or service restarts.

### Configuration
Controlled via environment variables:
- `CELERY_BEAT_ENABLED`: Set to `true` to enable the beat process.
- `CELERY_BEAT_USE_DB_SCHEDULES`: Set to `true` to load schedules from the database.
- `CELERY_BEAT_DB_REFRESH_SECONDS`: Frequency (default 60s) at which Beat re-syncs with the DB.

### Database Schema (`celery_beat_schedules`)
Schedules are stored in the `celery_beat_schedules` table. Key fields include:
- `name`: Unique identifier for the schedule.
- `task`: Full python path to the task (e.g., `celery_tasks.tasks.maintenance_tasks.refresh_views`).
- `schedule_type`: Either `interval` (fixed seconds) or `crontab` (standard cron format).
- `enabled`: Boolean toggle.
- `kwargs`: JSON object containing arguments passed to the task (e.g., `{"hospital_id": 1}`).

### Managing Schedules
Schedules are managed via the Admin UI at `/admin/celery-schedules`.

1.  **Interval Schedules**: Define `interval_seconds`.
2.  **Crontab Schedules**: Define standard cron fields (`minute`, `hour`, etc.).
3.  **Scoping**: Use the `kwargs` field to scope tasks to specific hospitals or users.

**Note:** The Beat process (`celery_tasks/beat_scheduler.py`) queries the DB every refresh interval. If a task is modified or disabled in the UI, the changes take effect within 60 seconds.

---

## Common Pitfalls & Learnings

Based on recent implementations of high-volume async workflows, observe the following best practices:

### 1. Memory Management & OOM
- **Issue**: Processing large high-resolution images (EXIF stripping, complex resizing) consumes significant RAM. Default Docker memory limits (512MB) may cause OOM kills.
- **Solution**: Monitor worker memory usage and set appropriate limits. For this project, `celery-ocr-worker` requires **2GB** and `celery-general-worker` requires **1GB** for stability.

### 2. Explicit Database Commits
- **Issue**: Sub-tasks in a chain often operate in their own transaction scope. Forgetting to `commit()` inside a task (expecting the parent to do it) leads to "missing" data records.
- **Solution**: Every task that performs a DB write must explicitly call `session.commit()`. Always wrap task logic in `try/except/finally` to ensure `session.rollback()` on error and `session.close()` at the end.

### 3. File System Synchronization
- **Issue**: A coordinator task extracts files, and workers immediately try to read them. If the extraction directory wasn't created with `parents=True`, workers will throw `FileNotFoundError`.
- **Solution**: Use `pathlib.Path.mkdir(parents=True, exist_ok=True)` in the coordinator *before* extraction.

### 4. Handling "Zombie" Tasks
- **Issue**: Redis persists tasks. If you purge the file system or database during development, old tasks in the queue will fail when picked up by workers.
- **Solution**: Implement graceful handling for `FileNotFoundError` in tasks. Periodically flush Redis (`redis-cli FLUSHALL`) in development environments after major data wipes.

### 5. Aggregate Status Management
- **Issue**: In a fan-out architecture, the parent job doesn't know when it's "done" because it only triggered the children.
- **Solution**: Implement a terminal check (e.g., `check_and_complete_job`) called by the *last* task in every sub-chain. This helper should query the DB to see if *all* siblings are in a terminal state.

### 6. Verbose Error Reporting
- **Issue**: "Internal Processing Error" is unhelpful for users.
- **Solution**: Capture the `str(exception)` in the task's `except` block and pass it to the `JobStore`. This allows the UI to show specific errors (e.g., "Malicious ZIP detected" or "Corrupt JPEG header").

---

## Adding a New Task (Step-by-Step)

```python
from utils.celery_helpers import enqueue_task

enqueue_task(
    "celery_tasks.tasks.thumbnail_tasks.process_thumbnail_job_task",
    args=[job_id],
    kwargs={"user_id": current_user.id, "hospital_id": hospital_id},
    queue="thumbnails",
)
```
