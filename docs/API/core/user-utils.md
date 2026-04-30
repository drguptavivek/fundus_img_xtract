# User Utils API

These are small lookup helpers used by the upload UI to discover the current user’s eligible lab units and hospitals.

Auth and CSRF:

- Both routes require a logged-in session and the roles listed below.
- Both routes are `GET`, so no CSRF token is required.

## Routes

| Route | Method | Auth | Response | Status codes |
| --- | --- | --- | --- | --- |
| `/api/eligibleLabUnit` | `GET` | Session + login + `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`, `fileUploader` | `{ "user_id": int, "hospital_id": int \| null, "is_master_admin": bool, "eligible_lab_units": [{"id": int, "name": str, "hospital_id": int, "hospital_name": str \| null}] }` | `403` on role failure. |
| `/api/eligibleLabUnitCurrentUser` | `GET` | Same role set as above | `{ "user_id": int, "hospital_id": int \| null, "is_master_admin": bool, "eligible_lab_units": [...], "eligible_hospitals": [{"id": int, "name": str}] }` | `403` on role failure. |

## `GET /api/eligibleLabUnit`

This route always uses `current_user.id` and `current_user.hospital_id` as the scope anchor.

Example:

```json
{
  "user_id": 12,
  "hospital_id": 3,
  "is_master_admin": false,
  "eligible_lab_units": [
    { "id": 10, "name": "Retina Clinic", "hospital_id": 3, "hospital_name": "City Eye Hospital" }
  ]
}
```

## `GET /api/eligibleLabUnitCurrentUser`

This route returns the same eligible lab-unit list and also includes the hospitals visible to the current user.

Example:

```json
{
  "user_id": 12,
  "hospital_id": 3,
  "is_master_admin": true,
  "eligible_lab_units": [],
  "eligible_hospitals": [
    { "id": 3, "name": "City Eye Hospital" }
  ]
}
```
