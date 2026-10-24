# IITK image re-pull

Restores full-fidelity IITK images that the old metadata strip re-encoded at JPEG quality 75 (see
[Remidio image re-pull](../remidio-image-repull/README.md) for the background). IITK images are fetched
by session id and source filename, which are stored on the session link and the image metadata, so no
signed links are involved.

The job finds IITK-linked EncounterSet images whose stored file still has the quality-75 signature,
downloads them again, strips metadata losslessly and overwrites the file in place (atomic replace).
**It writes nothing to the database**: no metadata extraction, no PII scan, no row changes. Thumbnails,
`edited_filename` derivatives and the stored `file_hash` are not rebuilt. If the provider's file size no
longer matches the synced size, the image is skipped (`source_changed`): a normal resync owns it.

Module: `iitk_api_integration/image_repull.py`. Task: `celery_tasks.tasks.iitk_tasks.repull_iitk_images_task`
(queue `maintenance`, general worker; restart the worker before the new task name is registered).

## `POST /api/admin/iitk/image-repull`

Admin role only; CSRF token required (`X-CSRFToken`); rate limited to 10 per hour.

| JSON field | Default | Meaning |
|---|---|---|
| `limit_images` | 50 | Damaged images per batch (1-200). A batch always finishes the capture day it is on. |
| `before` | none | Only encounters captured before this date (`YYYY-MM-DD`): pass the previous run's `next_before`. |
| `batches` | 1 | Batches to chain (1-500), 30 s apart. Work goes **newest first, backwards**. |
| `dry_run` | false | Count damaged images only; no IITK calls, no writes. |

Response `202`: `{"queued": true, "task_id": "..."}`; invalid input returns `400`.

Task result: `encounters`, `candidates`, `replaced`, `already_ok`, `missing_file`, `not_returned_by_source`,
`source_changed`, `source_is_quality_75`, `failed`, `errors`, `next_before`, `done`. Re-running is safe. If
`failed` is above 0, re-run without `before` and confirm with the file scan.

Every restored image is appended as one JSON line to `logs/iitk_image_repull.jsonl` (`IITK_REPULL_LOG`),
so `wc -l` is the number healed.

Pacing: `IITK_REPULL_DOWNLOAD_PAUSE_SECONDS` (default 1.0) and `IITK_REPULL_ENCOUNTER_PAUSE_MIN_SECONDS` /
`..._MAX_SECONDS` (default 3 and 8, random gap between encounters).
