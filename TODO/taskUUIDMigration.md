# Task UUID Migration

## Goal
Stop exposing sequential `GradingTask.id` values in URLs and forms by switching to non‑guessable UUIDs everywhere the client references a task.

## Work Breakdown
1. **Schema support** – add a `uuid` column to `grading_tasks`, defaulting to `uuid4`, indexed + unique. Update the ORM model and document manual backfill steps for existing rows. *(completed: column added in `models.GradingTask`)*

ALTER TABLE grading_tasks ADD COLUMN uuid TEXT UNIQUE;
CREATE INDEX IF NOT EXISTS ix_grading_tasks_uuid ON grading_tasks (uuid);



2. **Data migration** – run a one-off script (via `uv run`) that populates missing UUIDs on existing tasks. Script landed in `scripts/backfill_task_uuid.py`; execute `uv run python -m scripts.backfill_task_uuid` (optionally `--dry-run`) on each environment.
3. **Server routing** – change all blueprint routes (`dual_grading_task`, `dual_grading_submit`, intra-rater resume, etc.) to accept `<task_uuid>` instead of integer IDs, and resolve the task via UUID server-side. *(dual grading + intra-rater redirects now emit UUIDs; audit remaining entry points)* 
4. **Template/form updates** – ensure every template or JS snippet that currently uses `task.id` for client communication switches to `task.uuid`. Continue to show the numeric ID only for display/audit contexts. *(dual grading template switched to uuid hidden fields; confirm other templates later)*
5. **Client-side JS** – rename globals like `window.taskId` to `window.taskUuid`, update `dual-grading-task.js` storage keys, and make sure localStorage cleanup handles legacy keys so users do not leak drafts. *(dual grading now passes UUID via `window.taskId`; storage logic still compatible but legacy cleanup update TBD)*
6. **Cross-cutting validations** – audit notifications/logging, ensure `TaskTracker` references still use integer IDs internally, and add regression tests that prove guessing a sequential ID no longer works.

## Manual Backfill Reminder
After deploying the schema change, run a short Python script in the project root (e.g., `uv run python -m scripts.backfill_task_uuid`) that assigns `uuid4()` to every task with `uuid IS NULL`. Keep this script idempotent.
