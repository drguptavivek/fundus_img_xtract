# Lab Units

Base path: `/api`

These routes live in `api/labUnits.py`.

## CSRF

- No CSRF token is required.
- All routes here are `GET` only.

## Auth and Roles

- These routes require `login_required`.
- They also require one of these roles unless the user is a master admin: `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`, `fileUploader`.
- A role failure returns `403 Forbidden`.
- An unauthenticated session is redirected by Flask-Login to the login flow.

## `GET /labunits`

Success response: `200 OK`

```json
[
  {
    "id": 10,
    "name": "Retina Clinic",
    "hospital_id": 1,
    "hospital_name": "Hospital A"
  }
]
```

Top-level response shape:
- JSON array of lab-unit objects

Lab-unit object keys:
- `id`
- `name`
- `hospital_id`
- `hospital_name`

Field notes:
- Results are ordered by `LabUnit.name.asc()`.
- Each row includes `hospital_name` via `selectinload(LabUnit.hospital)`.

## `GET /labunits/<lab_unit_id>`

Path parameter:
- `lab_unit_id`: integer lab-unit ID

Success response: `200 OK`

```json
{
  "id": 10,
  "name": "Retina Clinic",
  "hospital_id": 1,
  "hospital_name": "Hospital A"
}
```

Errors:
- `404` with `{"error":"Lab unit not found or access denied"}` when the record is missing or the current user cannot see it

## `GET /hospitals/<hospital_id>/labunits`

See [Hospitals and Lab Units](hospitals.md) for the nested hospital route.
