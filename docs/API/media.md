# Media APIs

These endpoints support thumbnail maintenance, status checks, and media-related admin tooling.

## `GET /api/thumbnails/job/<job_token>/status`

Returns `{"status": object}` for a thumbnail job.

## `POST /api/thumbnails/cleanup`

Returns a JSON object describing the cleanup outcome.

## `POST /api/thumbnails/batch`

Returns a JSON object describing the batch operation outcome.

## Admin thumbnail management API

The admin dashboard also exposes:

- `GET /admin/api/thumbnail_stats`
- `GET /admin/api/maintenance_status`
- `GET /admin/api/thumbnail/health_check`
- `POST /admin/api/thumbnail/manual_maintenance`
- `POST /admin/api/thumbnail/cleanup_orphaned`
- `POST /admin/api/thumbnail/regenerate_missing`
- `POST /admin/api/thumbnail/validate_integrity`
- `POST /admin/api/thumbnail/full_maintenance`

## Notes

- These routes are consumed by dashboard JS, not mobile clients.
- Keep the response keys stable because the maintenance UI reads them directly.
