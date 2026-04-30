# Operation Scoping

This page describes the behavior of `GET /api/scoping/operation/<operation_name>`.

## Response Shape

```json
{
  "operation": "grading",
  "is_cross_hospital": true,
  "user_is_master_admin": true,
  "show_hospital_filter": true
}
```

## Contract Notes

- The endpoint is read-only.
- It does not accept a request body.
- `show_hospital_filter` is a UI hint, not an authorization check.
- The current implementation does not use `is_cross_hospital` to decide whether the filter is visible; only `current_user.is_master_admin` controls that field.

## Status Codes

- `200` success
- `302` unauthenticated session redirect

## CSRF

- No CSRF token is required.
