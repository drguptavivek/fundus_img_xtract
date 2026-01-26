# Handoff (Next Coding Session)

Date: 2026-01-26

## Current State

### Celery
- Celery foundation is in place (workers, routing, enqueue helpers, DB-backed Beat schedules).
- Beat scheduler now converts DB schedule dicts into `ScheduleEntry` objects to avoid `is_due` errors.
- `celery-ocr-worker` and `celery-general-worker` are wrapped with watchdog auto-restart in `docker-compose.override.yml`.
- Beat runs with `DatabaseScheduleScheduler` and should no longer crash.

### S3 / Storage
- S3 global prefix enforced (`eyeimgmgr/`), no per-hospital prefix.
- S3 keys derived from local paths, mirroring `/files` structure.
- Non-ASCII filenames are sanitized to ASCII-friendly variants (do not reject).
- Path validation updated and tested.

### Docs
- `docs/10-DEVELOP/celery-setup.md` added (setup and runtime info).
- `docs/10-DEVELOP/celery-integration.md` added (integration, scheduling, logging, failures).

## Open Work / Next Steps

1) **Commit docs**
   - `docs/10-DEVELOP/celery-setup.md`
   - `docs/10-DEVELOP/celery-integration.md`
2) **Confirm Beat + Worker stability**
   - Ensure Celery Beat runs without `is_due` errors.
   - Ensure workers restart correctly under watchdog.
3) **Validate schedule creation**
   - Create a schedule in `/admin/celery-schedules` and verify execution.
4) **Queue usage**
   - Confirm tasks enqueue with correct queue + kwargs (`user_id`, `hospital_id`).
5) **Test pass**
   - Run tests in Docker (see commands below).

## Current Gaps / Issues to Address

- Docs not committed yet (`celery-setup.md`, `celery-integration.md`, `handoff.md`).
- Verify Celery Beat schedule creation and task execution end-to-end.
- Confirm all Celery task enqueue sites include `user_id` / `hospital_id`.
- Ensure watchdog auto-reload works in local dev (not for prod).

## Tests / Verification to Run

```
DC="docker compose --env-file deploy.config.env --env-file deploy.secrets.env"
$DC exec -u $(id -u):$(id -g) web uv run pytest tests/
```

Targeted tests:
```
$DC exec -u $(id -u):$(id -g) web uv run pytest tests/test_s3_paths.py -v
```

## Commands (Quick Reference)

Start services:
```
$DC up -d web celery-ocr-worker celery-general-worker celery-beat
```

Logs:
```
$DC logs -f celery-ocr-worker
$DC logs -f celery-general-worker
$DC logs -f celery-beat
```

Restart workers:
```
$DC restart celery-ocr-worker celery-general-worker
```

## Notes / Risks

- Beat uses DB schedules; no restart needed for schedule changes.
- Celery auto-reload is via watchdog (not Celery built-in).
- Do **not** delete job records for failed tasks; requeue instead.

## Logical Reasoning / Decisions

- **DB-backed schedules**: Avoids restarts when schedule changes; Beat refreshes on a short interval.
- **Separate workers**: OCR and heavy CPU queues isolated to prevent UI starvation.
- **Local-first uploads**: Ensures data safety even if S3 fails; S3 migration is asynchronous.
- **Global S3 prefix**: Enforces consistent storage layout across all hospitals/buckets.
- **Non-ASCII filenames**: Sanitized to ASCII instead of rejected to avoid data loss.
