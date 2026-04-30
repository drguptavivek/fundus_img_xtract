# Disease Lookups

Base path: `/api`

These routes live in `api/disease.py`.

## CSRF

- No CSRF token is required.
- All routes here are `GET` only.

## Auth and Roles

- These routes require `login_required` through `roles_required`.
- Allowed roles: `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist`.
- `fileUploader` is not included on this surface.
- A role failure returns `403 Forbidden`.
- An unauthenticated session is redirected by Flask-Login to the login flow.

## `GET /disease-grades/<disease_id>`

Path parameter:
- `disease_id`: integer disease ID

Success response: `200 OK`

```json
{
  "grades": [
    { "id": 7, "impression": "Mild NPDR" },
    { "id": 8, "impression": "Non Gradable" }
  ]
}
```

Top-level response keys:
- `grades`

`grades` item keys:
- `id`
- `impression`

Field notes:
- The route returns disease-specific grades plus common grades named `Other Retinal` and `Non Gradable`.
- Duplicate grades are de-duplicated by `id` before serialization.

## `GET /diseases-with-gradings`

Success response: `200 OK`

```json
{
  "diseases": [
    {
      "id": 1,
      "name": "Diabetic Retinopathy",
      "gradings": [
        { "id": 7, "impression": "Mild NPDR" }
      ]
    }
  ]
}
```

Top-level response keys:
- `diseases`

`diseases` item keys:
- `id`
- `name`
- `gradings`

`gradings` item keys:
- `id`
- `impression`

## `GET /diseases-gradings-features/<disease_id>`

Path parameter:
- `disease_id`: integer disease ID

Success response: `200 OK`

```json
{
  "disease": {
    "id": 1,
    "name": "Diabetic Retinopathy",
    "gradings": [
      {
        "id": 7,
        "impression": "Mild NPDR",
        "display_order": 1,
        "is_active": true,
        "guidelines": "Example guidelines",
        "features": [
          { "id": 101, "sr_no": 1, "label": "Microaneurysms" }
        ]
      }
    ]
  }
}
```

Top-level response keys:
- `disease`

`disease` keys:
- `id`
- `name`
- `gradings`

`gradings` item keys:
- `id`
- `impression`
- `display_order`
- `is_active`
- `guidelines`
- `features`

`features` item keys:
- `id`
- `sr_no`
- `label`

Errors:
- `404` with `{"error":"Disease not found"}` when the disease does not exist
