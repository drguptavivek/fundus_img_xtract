# Status and Monitoring

This page covers the admin status dashboard and its JSON APIs.

## Routes

- `GET /admin/status`
- `GET /admin/api/admin/status`
- `GET /admin/api/celery/tasks/status`
- `GET /admin/api/sequences/status`
- `POST /admin/sequences/refresh`

## `GET /admin/status`

HTML dashboard for admins and data managers.

Auth:
- `@roles_required("admin", "data_manager")`

Response:
- `200 OK` HTML rendered from `templates/admin/status.html`

Data shown by the page:
- `thumbnail_stats`
- `maintenance_status`
- `health_status`
- `system_stats`
- `recent_activity`
- `sequence_report`
- `celery_status`
- `scoped_users`
- `grading_inconsistency_count`
- `linked_task_inconsistency_count`
- `review_consensus_mismatch_count`
- `current_time`

## `GET /admin/api/admin/status`

JSON summary for dashboard polling.

Auth:
- `@roles_required("admin", "data_manager")`

Response `200`:
```json
{
  "success": true,
  "data": {
    "timestamp": "2026-04-30T12:00:00+00:00",
    "thumbnail": {},
    "maintenance": {},
    "health": {},
    "system": {},
    "recent_activity": [],
    "celery": {}
  }
}
```

Response `500`:
```json
{
  "success": false,
  "error": "message",
  "timestamp": "2026-04-30T12:00:00+00:00"
}
```

## `GET /admin/api/celery/tasks/status`

JSON Celery schedule/task diagnostics.

Auth:
- `@roles_required("admin", "data_manager")`

Response `200`:
```json
{
  "success": true,
  "data": {
    "timestamp": "2026-04-30T12:00:00+00:00",
    "summary": {
      "total": 0,
      "db_entries": 0,
      "code_entries": 0,
      "warning_count": 0,
      "disabled_count": 0
    },
    "rows": []
  }
}
```

Each `rows[]` entry contains:
- `name`
- `task_name`
- `source` (`db` or `code`)
- `queue`
- `queue_explicit`
- `enabled`
- `schedule_type`
- `schedule`
- `last_run_at`
- `next_run_at`
- `status`
- `issues`

## `GET /admin/api/sequences/status`

Returns the sequence-vs-table-max diagnostic report.

Auth:
- `@roles_required("admin", "data_manager")`

Response `200`:
```json
{ "success": true, "data": {} }
```

Response `500`:
```json
{ "success": false, "error": "message" }
```

## `POST /admin/sequences/refresh`

Resets sequences to table maxima.

Auth:
- `@roles_required("admin")`

CSRF:
- Required. The page flow is a normal form POST and must include `{{ csrf_field() }}`.

Response:
- `302` redirect back to `/admin/status`
- Flash on success or failure

## CSRF Rules

- `POST /admin/sequences/refresh` is form-posted and CSRF protected.
- The JSON polling endpoints above are `GET` and do not use CSRF.
