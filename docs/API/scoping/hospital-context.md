# Hospital Context

Base path: `/api`

These routes live in `api/scoping.py`.

## CSRF

- No CSRF token is required.
- Both routes are `GET` only.

## `GET /user/hospital-context`

Auth: `login_required`

Success response: `200 OK`

```json
{
  "user_id": 123,
  "is_master_admin": false,
  "hospital_id": 5,
  "hospital_name": "Mobile Hospital",
  "can_access_multiple_hospitals": false
}
```

Top-level response keys:
- `user_id`
- `is_master_admin`
- `hospital_id`
- `hospital_name`
- `can_access_multiple_hospitals`

Field notes:
- `hospital_name` is `null` when the current user has no hospital record.
- `can_access_multiple_hospitals` currently mirrors `is_master_admin`.

Errors:
- Unauthenticated requests are redirected by Flask-Login to the login flow.

## `GET /scoping/operation/<operation_name>`

Auth: `login_required`

Path parameter:
- `operation_name`: the operation name to inspect, such as `grading`, `upload`, or `analytics`

Success response: `200 OK`

```json
{
  "operation": "grading",
  "is_cross_hospital": false,
  "user_is_master_admin": false,
  "show_hospital_filter": false
}
```

Top-level response keys:
- `operation`
- `is_cross_hospital`
- `user_is_master_admin`
- `show_hospital_filter`

Field notes:
- `is_cross_hospital` comes from `utils.hospital_scoping.is_cross_hospital_operation(operation_name)`.
- `show_hospital_filter` currently mirrors `current_user.is_master_admin`, not `is_cross_hospital`.

Errors:
- Unauthenticated requests are redirected by Flask-Login to the login flow.
