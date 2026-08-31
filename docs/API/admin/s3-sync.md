# S3 Sync Status

This page documents the S3 sync dashboard and its JSON controls.

Every route in this surface requires the global `admin` role. Hospital selection
is an administrative filter, not a delegated hospital or project permission.

## Routes

- `GET /admin/s3-sync-dashboard`
- `GET /admin/s3-sync-dashboard/hospital/<int:hospital_id>`
- `GET /admin/api/s3-sync-status`
- `POST /admin/api/s3-sync-retry/<int:sync_id>`
- `GET /admin/api/s3-sync-stats`

## `GET /admin/s3-sync-dashboard`

HTML dashboard.

Auth:
- `@roles_required("admin")`

Response:
- `200 OK` HTML rendered from `templates/admin/s3_sync_dashboard.html`

## `GET /admin/s3-sync-dashboard/hospital/<hospital_id>`

HTML detail page for one hospital.

Auth:
- `@roles_required("admin")`

Response:
- `200 OK` HTML rendered from `templates/admin/s3_sync_hospital_detail.html`
- `302` redirect with flash if the hospital/config does not exist

## `GET /admin/api/s3-sync-status`

Query params:
- `hospital_id` optional integer
- `status` optional string (`pending`, `success`, `failed`, `in_progress`)
- `limit` optional integer, default `50`

Auth:
- `@roles_required("admin")`

Response `200`:
```json
{
  "syncs": [
    {
      "id": 1,
      "file_type": "direct_upload",
      "file_id": 10,
      "variant": "original",
      "status": "failed",
      "attempt_count": 2,
      "last_error": "message",
      "last_attempt_at": "2026-04-30T12:00:00+00:00",
      "synced_at": "2026-04-30T12:00:00+00:00",
      "created_at": "2026-04-30T12:00:00+00:00"
    }
  ],
  "count": 1
}
```

Error responses:
- `403 {"error":"Access denied"}`
- `404 {"error":"No S3 config for hospital"}`

## `POST /admin/api/s3-sync-retry/<sync_id>`

Marks a failed sync as `in_progress`.

Auth:
- `@roles_required("admin")`

CSRF:
- Required if called from browser JS. The dashboard JS sends `X-CSRFToken`.

Request:
- No JSON body required.

Success `200`:
```json
{
  "success": true,
  "message": "Sync marked for retry",
  "sync_id": 123
}
```

Error responses:
- `404 {"success": false, "message": "Sync record not found"}`
- `404 {"success": false, "message": "S3 config not found"}`
- `403 {"success": false, "message": "Access denied"}`
- `400 {"success": false, "message": "Only failed syncs can be retried (current: ... )"}`

## `GET /admin/api/s3-sync-stats`

Response `200`:
```json
{
  "stats": [
    {
      "hospital_id": 1,
      "hospital_name": "Hospital A",
      "pending": 0,
      "success": 0,
      "failed": 0,
      "in_progress": 0,
      "has_s3": true,
      "s3_config_id": 9
    }
  ]
}
```

## CSRF Rules

- The retry action is the only JSON mutation in this surface.
- The page JS includes the CSRF token in `X-CSRFToken`.
- The dashboard and stats endpoints are `GET` and do not require CSRF.
