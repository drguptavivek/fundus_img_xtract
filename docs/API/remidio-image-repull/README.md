# Remidio image re-pull

Restores full-fidelity Remidio images that the old metadata strip re-encoded at JPEG quality 75.
The strip decoded every pixel and re-saved it with Pillow's default quality; it now removes metadata
segments only (`utils/image_processing.strip_exif_data`), so new images are untouched.

Remidio file links are signed and expire, so the job asks the Remidio API for each site/day again
(fresh links), downloads only the images whose stored file still has the quality-75 signature, strips
them losslessly and overwrites the file in place (atomic replace). **It writes nothing to the database**:
no OCR re-run, no metadata or row changes. Thumbnails and `edited_filename` derivatives are not rebuilt.
Only images are re-pulled, never PDFs or reports. Only Remidio-sourced images are covered; IITK images need their own re-pull.

Module: `remidio_api_integration/image_repull.py`. Task:
`celery_tasks.tasks.remidio_tasks.repull_remidio_images_task` (queue `maintenance`, general worker;
a worker restart is needed before a new task name is registered).

## `POST /api/admin/remidio/image-repull`

Admin role only; CSRF token required (`X-CSRFToken`); rate limited to 10 per hour.

| JSON field | Default | Meaning |
|---|---|---|
| `limit_images` | 50 | Damaged images per batch (1-200). A batch always finishes the exam day it is on. |
| `before` | none | Only exams older than this date (`YYYY-MM-DD`): pass the previous run's `next_before` to continue. |
| `batches` | 1 | Batches to chain (1-500), 30 s apart. Work goes **newest exam first, backwards**. |
| `dry_run` | false | Count damaged images only; no Remidio calls, no writes. |

Response `202`: `{"queued": true, "task_id": "..."}`. Validation failures return `400` with
`{"error": "invalid_request", "message": "..."}`.

Task result (see `celery-general-worker` logs / result backend): `groups`, `candidates`, `replaced`,
`already_ok`, `missing_file`, `not_returned_by_source`, `source_is_quality_75`, `failed`, `errors`,
`next_before`, `done`. Re-running is safe: images already restored no longer match the signature.

```bash
curl -X POST https://HOST/api/admin/remidio/image-repull \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" --cookie "$SESSION" \
  -d '{"limit_images": 50, "batches": 100, "dry_run": true}'
```

Every restored image is logged (`Remidio image restored image=... encounter=... bytes before -> after`) and
appended as one JSON line to `logs/remidio_image_repull.jsonl` (`REMIDIO_REPULL_LOG` to move it), so
`wc -l` on that file is the number healed.

Pacing: `REMIDIO_REPULL_PAUSE_SECONDS` (default 2.5, per Remidio API call),
`REMIDIO_REPULL_DOWNLOAD_PAUSE_SECONDS` (default 1.0, per download) and
`REMIDIO_REPULL_ENCOUNTER_PAUSE_SECONDS` (default 10, extra gap between encounters).

## Remidio ingestion no longer runs the PII scan

`queue_image_post_processing(..., run_pii=False)` is used for Remidio syncs: metadata extraction and the
lossless EXIF strip still run, the burned-in-PII scan does not (IITK keeps it). No `ImagePiiVerification`
row is written for these images.
