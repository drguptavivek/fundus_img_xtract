# Rate Limits

This page documents the admin rate-limit dashboard and its JSON helpers.

## Routes

- `GET /admin/rate-limits/`
- `POST /admin/rate-limits/clear`
- `GET /admin/rate-limits/status`
- `GET /admin/rate-limits/my-key`
- `POST /admin/rate-limits/clear-all`
- `POST /admin/rate-limits/clear-limit-ajax`

## `GET /admin/rate-limits/`

HTML dashboard.

Auth:
- `@roles_required("admin")`

Response:
- `200 OK` HTML rendered from `templates/admin/rate_limits/index.html`

The template consumes:
- `stats`
- `limits`
- `current_page`
- `per_page`

## `POST /admin/rate-limits/clear`

CSRF:
- Required

Form fields:
- `key`
- `limit` optional

Behavior:
- Clears the matching rate-limit bucket and redirects back to the index

## `GET /admin/rate-limits/status`

Auth:
- `@login_required`
- `@conditional_exempt(...)`

Query params:
- `key` optional string

Response:
- JSON object from `utils.rate_limiter.get_rate_limit_status()`
- The dashboard expects keys such as `key`, `matching_keys`, and `limits`

## `GET /admin/rate-limits/my-key`

Response `200`:
```json
{ "key": "user:123" }
```

## `POST /admin/rate-limits/clear-all`

CSRF:
- Required

Form fields:
- `confirm` must equal `CLEAR_ALL_RATE_LIMITS`

Behavior:
- Clears every rate-limit bucket
- Redirects back to the dashboard with flash messages

## `POST /admin/rate-limits/clear-limit-ajax`

Request JSON:
```json
{ "key": "ip:127.0.0.1" }
```

Success `200`:
```json
{
  "success": true,
  "message": "Rate limit cleared successfully for key: ip:127.0.0.1"
}
```

Validation/error responses:
- `400 {"success": false, "message": "Key is required to clear a rate limit"}`
- `500 {"success": false, "message": "Failed to clear rate limit. Check logs for details."}`

## CSRF Rules

- The form posts require CSRF.
- The AJAX clear call sends `X-CSRFToken` from `{{ csrf_token() }}`.
- `GET /status` and `GET /my-key` do not require CSRF.
