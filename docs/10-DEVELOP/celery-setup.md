# Celery Setup

This document describes how to run Celery workers and Celery Beat in this project.

## Overview

- Celery is used for background processing (OCR, PII, thumbnails, metadata, exports, maintenance).
- Redis is the broker and result backend.
- Celery Beat schedules are stored in the database and refreshed without restarting Beat.
- Workers are split by queue (OCR vs general).

## Services

Docker Compose services:
- `celery-ocr-worker`: CPU-heavy queues (`zip_ocr`, `pii_detection`, `pdf_processing`)
- `celery-general-worker`: general queues (`thumbnails`, `metadata`, `exports`, `maintenance`, `s3_sync`)
- `celery-beat`: schedule runner (DB-backed)

## Configuration

Required env vars:
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`
- `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `CELERY_ENABLED=true`
- `CELERY_BEAT_ENABLED=true`
- `CELERY_BEAT_USE_DB_SCHEDULES=true`
- `CELERY_BEAT_DB_REFRESH_SECONDS=60`

Defaults are in `deploy.config.env` and `deploy.config.env.example`.

## Running (Docker)

Start services:

```
DC="docker compose --env-file deploy.config.env --env-file deploy.secrets.env"
$DC up -d web celery-ocr-worker celery-general-worker celery-beat
```

Logs:

```
$DC logs -f celery-ocr-worker
$DC logs -f celery-general-worker
$DC logs -f celery-beat
```

## Database Schedules (Beat)

Schedules are stored in `celery_beat_schedules` and loaded by Beat at runtime.
Create or edit schedules via the admin UI:

```
/admin/celery-schedules
```

Notes:
- Schedules are global. `hospital_id` can be set to scope task kwargs.
- Every schedule carries `user_id` and `hospital_id` in kwargs.
- Changes are picked up without restarting Beat (refresh window default 60s).

## Development Auto-Reload

Celery does not support `--autoreload`. For development, use `watchmedo`:

```
uv run python -m watchdog.watchmedo auto-restart \
  --directory=./ --pattern=*.py --recursive -- \
  celery -A celery_worker worker --loglevel=info
```

The dev override uses this pattern:
`docker-compose.override.yml` / `docker-compose.override.yml.example`

Do **not** use auto-reload in production.

## Queues

Queue mapping (configured in `celery_app.py`):
- `zip_ocr`: ZIP OCR and heavy OCR tasks
- `pii_detection`: PII detection jobs
- `pdf_processing`: PDF OCR
- `thumbnails`: thumbnail generation
- `metadata`: metadata extraction/backfill
- `exports`: report/export jobs
- `maintenance`: cleanup, maintenance tasks
- `s3_sync`: local -> S3 migrations

## Migrations

When adding or changing schedules, ensure the DB is migrated:

```
$DC exec -u $(id -u):$(id -g) web uv run alembic upgrade head
```

## Testing

Run tests in Docker:

```
$DC exec -u $(id -u):$(id -g) web uv run pytest tests/
```
