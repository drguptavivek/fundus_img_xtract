# Direct Uploads API

These endpoints support direct-upload clients and lookup helpers used by the upload UI.

Auth and CSRF:

- All routes require a logged-in session and the listed roles.
- All routes are `GET`, so no CSRF token is required.

## Canonical routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/users/<int:user_id>/lab-units` | `GET` | Session + login + `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`, `fileUploader` | Path `user_id` must match `current_user.id` | Array of `{ "id": int, "name": str }` | `404` if the user does not exist. `403` if the caller asks for another user. |
| `/api/lab-units/<int:lab_unit_id>/hospital` | `GET` | Same role set as above | Path `lab_unit_id` | `{ "id": int, "name": str }` | `404` if the lab unit is missing or outside scope. |
| `/api/upload-jobs/<job_token>/status` | `GET` | Same role set as above | Path `job_token` | `{ "job_id": int, "job_token": str, "job_status": str, "items": [{"filename": str, "state": str, "detail": str \| null}] }` | `404` if the job is missing. `403` if the job is not owned by the caller and the lab unit is outside the caller’s allowed lab-unit IDs. |

### `GET /api/users/<int:user_id>/lab-units`

Response is the scoped list of lab units for the authenticated user.

```json
[
  { "id": 12, "name": "Retina Clinic" }
]
```

### `GET /api/lab-units/<int:lab_unit_id>/hospital`

Response is the hospital attached to the requested lab unit.

```json
{ "id": 3, "name": "City Eye Hospital" }
```

### `GET /api/upload-jobs/<job_token>/status`

`items` is ordered by `JobItem.id` and each item contains `filename`, `state`, and `detail`.

```json
{
  "job_id": 41,
  "job_token": "a1b2c3",
  "job_status": "processing",
  "items": [
    { "filename": "img001.jpg", "state": "completed", "detail": null }
  ]
}
```

## Legacy compatibility routes

The older direct-upload package exposes the same data under legacy paths:

| Legacy route | Method | Notes |
| --- | --- | --- |
| `/api/lab-units/<int:user_id>` | `GET` | Same payload shape as `/api/users/<int:user_id>/lab-units`, but this legacy route is rate-limited and returns `403` for unauthorized cross-user access. |
| `/api/hospital/<int:lab_unit_id>` | `GET` | Same payload shape as `/api/lab-units/<int:lab_unit_id>/hospital`, but this legacy route returns `403` if the lab unit is outside the caller’s allowed lab-unit IDs. |
| `/api/direct/upload/status/<job_token>` | `GET` | Same payload shape as `/api/upload-jobs/<job_token>/status`, but unauthorized or missing jobs are both reported as `404`. |
