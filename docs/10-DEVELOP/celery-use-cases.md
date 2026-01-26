# Celery Use Cases and Requirements

Status: Draft
Last Updated: 2026-01-26
Owner: Engineering

## Purpose

This document defines the required Celery use cases, triggers, schedules, and non-functional requirements. It is the source of truth for implementing the Celery foundation and task set. The implementation MUST follow these requirements.

This complements and should align with:
- plan/pii_celery_plan.md (PII/OCR design and worker isolation)

## Core Principles

1. Local-first data safety: uploads are always persisted locally first.
2. Background tasks must be idempotent and safe to retry.
3. Audit logging is mandatory for all task state changes.
4. Multi-tenant isolation: hospital-scoped tasks must not cross hospitals.
5. Consistent S3 path scheme: S3 keys mirror local /files path with a single global prefix (e.g., /eyeimgmgr/).

## Priority Focus (for initial Celery rollout)

Celery should first target CPU/memory intensive and high-volume workloads to relieve the web process:

- ZIP processing with OCR (CPU/memory heavy)
- PII extraction (CPU heavy)
- S3 local -> S3 migration (high-volume I/O)
- Thumbnail generation (high-volume)
- Metadata extraction/backfill (batchable, medium CPU)

Low-impact periodic jobs (materialized view refresh, stuck task cleanup) are NOT primary Celery targets.

## Task Inventory (MVP and Planned)

Each task MUST specify: queue, trigger, schedule, idempotency strategy, retry policy, and audit events.

### P0/P1 Tasks (Required for initial Celery rollout)

1) ZIP Processing + OCR
- Trigger: ZIP upload ingestion (Remedio / bulk ZIP).
- Queue: zip_ocr
- Schedule: immediate enqueue.
- Idempotency: unique by zip checksum or job token; skip if already processed.
- Retry: yes, limited backoff.
- Audit: job created, started, completed, failed.

2) PII Detection (image)
- Trigger: on image upload (direct and ZIP ingestion), and manual re-run.
- Queue: pii_detection
- Schedule: immediate enqueue; optional periodic backlog sweep.
- Idempotency: unique by (image_uuid, variant); skip if completed unless forced.
- Retry: yes, limited backoff; max attempts defined in Celery config.
- Audit: job created, started, completed, failed.

3) S3 Sync (local -> S3 migration)
- Trigger: manual by admin (per hospital); scheduled sweep (off-peak).
- Queue: s3_sync
- Schedule: nightly or configurable; on-demand per hospital.
- Idempotency: if s3_object_key already set and object exists, skip.
- Retry: yes, bounded; failures recorded with last_error.
- Audit: sync attempt, success, failure; include file_id and hospital_id.

4) Thumbnail Generation / Regeneration
- Trigger: on upload; post-processing after OCR/PII/metadata; manual re-run.
- Queue: thumbnails
- Schedule: immediate enqueue; optional periodic audit for missing thumbnails.
- Idempotency: skip if thumbnail exists and matches source.
- Retry: yes, limited.
- Audit: generation attempt, success, failure.

5) Metadata Extraction / Backfill
- Trigger: post-processing after OCR/PII; manual batch re-run.
- Queue: metadata
- Schedule: immediate enqueue; optional nightly backfill.
- Idempotency: skip if metadata exists with same hash.
- Retry: yes, bounded.
- Audit: start/end with counts.

### P2 Tasks (Planned)

6) PDF OCR (non-ZIP sources)
- Trigger: on PDF ingestion or manual request.
- Queue: pdf_processing
- Schedule: immediate enqueue.
- Idempotency: unique by (encounter_pdf_id, checksum) or (uuid, variant).
- Retry: yes, limited.
- Audit: job created, started, completed, failed.

7) Long-running imports (Excel/ZIP)
- Trigger: manual upload action.
- Queue: imports
- Schedule: immediate enqueue.
- Idempotency: use job token + file hash; skip duplicates.
- Retry: yes; use per-row error capture.
- Audit: job start/end, rows processed.

8) Report generation / exports
- Trigger: manual request.
- Queue: reports
- Schedule: on-demand.
- Idempotency: cache by params + time window where applicable.
- Retry: yes, limited.
- Audit: report generation attempt, success, failure.

### Low Priority (Non-critical Celery Beat candidates)

- Materialized view refresh (currently scheduled in-process)
- Stuck task cleanup
- Periodic thumbnail audits (if not urgent)

## Non-Functional Requirements

### Isolation and Imports
- Task modules MUST NOT import Flask app or blueprints.
- Use minimal task models or shared DB access utilities without app context.
- Avoid circular imports; follow plan/pii_celery_plan.md.

### Concurrency and Resource Limits
- Separate queues for CPU-heavy OCR vs general tasks.
- Default worker concurrency should be conservative (1-2) per worker.
- Respect infra limits (4 cores, 8GB RAM) as documented in plan/pii_celery_plan.md.

### Idempotency and Safety
- Each task must check for existing completion before doing work.
- Tasks must be safe to re-run and safe to retry after partial failure.
- Avoid destructive operations until the final step succeeds (e.g., delete local file only after S3 success and policy allows).

### Auditing and Monitoring
- All tasks must log to audit logger with hospital_id and file/task IDs.
- Persist job state where long-running or retryable tasks exist (e.g., S3 sync, PII jobs).
- Admin UI should surface:
  - per-hospital pending/failed counts
  - last run time
  - recent failures with error summary

## Task-to-Queue Mapping (Proposed)

- zip_ocr: ZIP processing + OCR
- pii_detection: PII detection tasks
- s3_sync: S3 migration tasks
- thumbnails: thumbnail generation/regeneration
- metadata: metadata backfill and consistency checks
- pdf_processing: PDF OCR tasks
- imports: ZIP/Excel ingestion (non-OCR)
- reports: report generation

## Required Interfaces

### Task Enqueue Helpers
- Provide helper functions to enqueue tasks from web routes.
- Helpers must validate inputs and record audit logs.

### Admin Controls
- Allow per-hospital:
  - run S3 sync now
  - view last error and failed items
  - pause/resume scheduled sync

### Schedule Management
- Celery Beat MUST load schedules from the database and refresh without restart.
- Schedule entries are global (applied across hospitals); hospital_id may be set to scope tasks.
- Every scheduled task MUST carry `user_id` and `hospital_id` in kwargs for audit scoping.
- Schedule changes should take effect within a short refresh window (default: 60s).

## Open Decisions

- Global S3 prefix constant: `eyeimgmgr/` (required).
- S3 sync schedule default: nightly window (exact time TBD).
- Retry policy defaults: max attempts and backoff values (align with Celery config).

## Acceptance Criteria

- Document reviewed and approved by engineering.
- Every Celery task in code references a documented use case from this file.
- Any new task must be added here before implementation.
