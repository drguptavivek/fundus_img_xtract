# Hospitals and Lab Units

Base path: `/api`

These routes live in `api/hospitals.py` and `api/labUnits.py`.

## CSRF

- No CSRF token is required.
- All routes here are `GET` only.

## Auth and Roles

- These routes require `login_required`.
- They also require one of these roles unless the user is a master admin: `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`, `fileUploader`.
- A role failure returns `403 Forbidden`.
- An unauthenticated session is redirected by Flask-Login to the login flow.

## `GET /hospitals`

Success response: `200 OK`

```json
[
  { "id": 1, "name": "Hospital A" },
  { "id": 2, "name": "Hospital B" }
]
```

Top-level response shape:
- JSON array of hospital objects

Hospital object keys:
- `id`
- `name`

Field notes:
- Results are ordered by `Hospital.name.asc()`.
- Results are filtered through `apply_scoping(..., Hospital, current_user, "view")`.

## `GET /hospitals/<hospital_id>`

Path parameter:
- `hospital_id`: integer hospital ID

Success response: `200 OK`

```json
{
  "id": 1,
  "name": "Hospital A"
}
```

Errors:
- `404` with `{"error":"Hospital not found or access denied"}` when the record is missing or the current user cannot see it

## `GET /hospitals/<hospital_id>/labunits`

Path parameter:
- `hospital_id`: integer hospital ID

Success response: `200 OK`

```json
[
  { "id": 10, "name": "Retina Clinic", "hospital_id": 1 },
  { "id": 11, "name": "Low Vision", "hospital_id": 1 }
]
```

Top-level response shape:
- JSON array of lab-unit objects

Lab-unit object keys:
- `id`
- `name`
- `hospital_id`

Field notes:
- Results are ordered by `LabUnit.name.asc()`.
- The query is scoped with `apply_scoping(..., LabUnit, current_user, "view")`.
- The route does not return a wrapper object and does not emit a 404 when a hospital has no visible lab units; it returns `[]`.
