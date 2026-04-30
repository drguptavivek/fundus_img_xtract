# Security and Support

This page documents the admin security tooling, audit views, and email/package scanning endpoints.

## Routes

- `GET /admin/change-password`
- `POST /admin/change-password`
- `GET /admin/roles`
- `GET /admin/role-usage`
- `GET /admin/routes-by-role/<string:role_name>`
- `GET /admin/sensitive-operations`
- `GET /admin/sensitive-operations/<int:log_id>`
- `GET /admin/security/cves`
- `GET /admin/api/security/cves/summary`
- `POST /admin/api/security/cves/refresh`
- `GET /admin/api/security/cves/history`
- `GET /admin/api/security/cves/packages`
- `GET /admin/api/security/cves/vulnerabilities`
- `GET /admin/api/security/cves/history/htmx`
- `GET /admin/security/cves/report.txt`
- `GET /admin/security/package-updates`
- `GET /admin/api/security/package-updates/summary`
- `POST /admin/api/security/package-updates/refresh`
- `GET /admin/api/security/package-updates/history`
- `GET /admin/api/security/package-updates/packages`
- `GET /admin/api/security/package-updates/history/htmx`
- `GET /admin/api/security/package-updates/updates.yaml`
- `GET /admin/api/security/package-updates/instructions`

## Password and RBAC views

### `GET/POST /admin/change-password`

Auth:
- `@roles_required("admin")`

GET response:
- HTML form

POST form fields:
- `username`

CSRF:
- Required via `{{ csrf_field() }}`

Behavior:
- Case-insensitive username lookup
- Generates a strong password, hashes it, clears lockout, emails the password reset

Response:
- HTML page `password_reset_done.html` on success
- HTML form re-render with flash on validation failure or missing user/email

### `GET /admin/roles`

Lists roles from the database.

Auth:
- `@roles_required("admin")`

### `GET /admin/role-usage`

Shows route-to-role analysis.

Auth:
- `@roles_required("admin")`

### `GET /admin/routes-by-role/<role_name>`

Shows the route inventory for one role.

Auth:
- `@roles_required("admin")`

## Sensitive operations audit

### `GET /admin/sensitive-operations`

Auth:
- `@roles_required("admin", "local_admin", "data_manager")`

Query params:
- `page` optional integer, default `1`
- `operation_type` optional string
- `status` optional string
- `username` optional string

Response:
- HTML page with `audit_logs`, `page`, `operation_types`, and the active filters

### `GET /admin/sensitive-operations/<log_id>`

Auth:
- `@roles_required("admin", "local_admin", "data_manager")`

Response `200`:
```json
{
  "id": 1,
  "operation_type": "database_dump",
  "status": "completed",
  "user": "admin",
  "ip_address": "127.0.0.1",
  "created_at": "2026-04-30T12:00:00+00:00",
  "request_details": {},
  "result_details": {}
}
```

Response `404`:
```json
{ "error": "Log entry not found" }
```

## CVE scanner

### `GET /admin/security/cves`

HTML report page.

Auth:
- `@roles_required("admin", "local_admin")`

Query params:
- `severity` optional (`critical`, `high`, `medium`, `low`)
- `scan_id` optional integer
- `trigger_scan` optional truthy flag

### `GET /admin/api/security/cves/summary`

Returns the latest summary from the database.

Auth:
- `@roles_required("admin", "local_admin")`

Response `200`:
```json
{
  "total": 0,
  "critical": 0,
  "high": 0,
  "has_critical_or_high": false,
  "last_scan": null,
  "scan_id": null,
  "error": null,
  "sources": []
}
```

### `POST /admin/api/security/cves/refresh`

Starts on-demand scans in the worker queues plus an inline web scan.

Auth:
- `@roles_required("admin")`

CSRF:
- Required. The page JS posts with `X-CSRFToken` when present.

Response `200`:
```json
{
  "success": true,
  "task_id": "celery-task-id",
  "tasks": [],
  "current_results": {},
  "message": "CVE scans started in background"
}
```

### `GET /admin/api/security/cves/history`

Returns recent scan rows.

Auth:
- `@roles_required("admin")`

Response:
```json
{ "scans": [] }
```

### `GET /admin/api/security/cves/packages`
### `GET /admin/api/security/cves/vulnerabilities`
### `GET /admin/api/security/cves/history/htmx`

HTML/HTMX fragments used by the CVE page.

### `GET /admin/security/cves/report.txt`

Downloads a plain-text CVE report.

Response:
- `200 OK`
- `Content-Type: text/plain; charset=utf-8`
- `Content-Disposition: attachment; filename="cve-report.txt"`

## Package updates

### `GET /admin/security/package-updates`

HTML package update report page.

Auth:
- `@roles_required("admin", "local_admin")`

### `GET /admin/api/security/package-updates/summary`

Returns the latest package-update summary object from the database.

Auth:
- `@roles_required("admin", "local_admin")`

Response `200`:
```json
{
  "updates_available": 0,
  "has_updates": false,
  "last_scan": null,
  "scan_id": null,
  "packages_scanned": 0,
  "error": null
}
```

### `POST /admin/api/security/package-updates/refresh`

Starts an on-demand package update scan.

Auth:
- `@roles_required("admin")`

CSRF:
- Required for browser POSTs.

Response `200`:
```json
{
  "success": true,
  "task_id": "celery-task-id",
  "current_results": {},
  "message": "Package update scan started in background"
}
```

### `GET /admin/api/security/package-updates/history`

Response:
```json
{ "scans": [] }
```

### `GET /admin/api/security/package-updates/packages`
### `GET /admin/api/security/package-updates/history/htmx`

HTMX fragments.

### `GET /admin/api/security/package-updates/updates.yaml`

Downloads a YAML file of packages with updates.

Response:
- `200 OK`
- `Content-Type: text/yaml`
- `Content-Disposition: attachment; filename=package-updates-<timestamp>.yaml`

### `GET /admin/api/security/package-updates/instructions`

Returns the update instructions view for the latest completed scan.

## CSRF Rules

- `POST /admin/change-password`, `POST /admin/api/security/cves/refresh`, and `POST /admin/api/security/package-updates/refresh` are browser mutations and must include CSRF.
- The GET report and history endpoints do not require CSRF.
