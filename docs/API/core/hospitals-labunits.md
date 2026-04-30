# Hospitals and Lab Units API

These routes expose hospital and lab-unit lookup data, filtered by the caller’s hospital scope.

Auth and CSRF:

- All routes are `GET`.
- They require a logged-in session and the roles listed below.
- No CSRF token is required.

## Routes

| Route | Method | Auth | Response | Status codes |
| --- | --- | --- | --- | --- |
| `/api/hospitals` | `GET` | Session + login + `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`, `fileUploader` | Array of `{ "id": int, "name": str }` | `403` on role failure. |
| `/api/hospitals/<int:hospital_id>` | `GET` | Same role set as above | `{ "id": int, "name": str }` | `404` if the hospital is missing or outside scope. |
| `/api/hospitals/<int:hospital_id>/labunits` | `GET` | Same role set as above | Array of `{ "id": int, "name": str, "hospital_id": int }` | `403` on role failure. |
| `/api/labunits` | `GET` | Same role set as above | Array of `{ "id": int, "name": str, "hospital_id": int, "hospital_name": str \| null }` | `403` on role failure. |
| `/api/labunits/<int:lab_unit_id>` | `GET` | Same role set as above | `{ "id": int, "name": str, "hospital_id": int, "hospital_name": str \| null }` | `404` if the lab unit is missing or outside scope. |

## `GET /api/hospitals`

Returns the hospitals visible to the current user.

## `GET /api/hospitals/<int:hospital_id>`

Returns the single hospital if it is visible to the current user.

## `GET /api/hospitals/<int:hospital_id>/labunits`

Returns the scoped lab units for the given hospital.

Example:

```json
[
  { "id": 10, "name": "Retina Clinic", "hospital_id": 3 }
]
```

## `GET /api/labunits`

Returns all scoped lab units with their hospital names preloaded.

Example:

```json
[
  {
    "id": 10,
    "name": "Retina Clinic",
    "hospital_id": 3,
    "hospital_name": "City Eye Hospital"
  }
]
```

## `GET /api/labunits/<int:lab_unit_id>`

Returns one scoped lab unit with its hospital name.

### Legacy compatibility

The older direct-upload compatibility module exposes:

- `GET /api/lab-units/<int:user_id>` for self-scope lab-unit lookup
- `GET /api/hospital/<int:lab_unit_id>` for a single hospital lookup by lab unit

Those aliases return the same shapes as the canonical lookup routes documented here, but with the legacy module’s own access checks and status-code behavior.
