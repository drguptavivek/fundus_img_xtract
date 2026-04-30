# Disease API

These endpoints return disease lookup data and grading hierarchies.

Auth and CSRF:

- All routes are `GET`.
- They require a logged-in session plus the roles listed below.

## Routes

| Route | Method | Auth | Response | Status codes |
| --- | --- | --- | --- | --- |
| `/api/disease-grades/<int:disease_id>` | `GET` | Session + login + `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `resident`, `optometrist` | `{ "grades": [{"id": int, "impression": str}] }` | `403` on role failure. |
| `/api/diseases-with-gradings` | `GET` | Same role set as above | `{ "diseases": [{"id": int, "name": str, "gradings": [{"id": int, "impression": str}]}] }` | `403` on role failure. |
| `/api/diseases-gradings-features/<int:disease_id>` | `GET` | Same role set as above | `{ "disease": {"id": int, "name": str, "gradings": [{"id": int, "impression": str, "display_order": int, "is_active": bool, "guidelines": str \| null, "features": [{"id": int, "sr_no": int, "label": str}]}]}}` | `404` if the disease is missing. `403` on role failure. |

## `GET /api/disease-grades/<int:disease_id>`

The route returns disease-specific grades plus the shared common grades hard-coded in the module:

- `Other Retinal`
- `Non Gradable`

Duplicates are removed by grade ID before serialization.

## `GET /api/diseases-with-gradings`

Returns every disease and its distinct gradings.

Example:

```json
{
  "diseases": [
    {
      "id": 1,
      "name": "Diabetic Retinopathy",
      "gradings": [
        { "id": 11, "impression": "Mild" }
      ]
    }
  ]
}
```

## `GET /api/diseases-gradings-features/<int:disease_id>`

The response is hierarchical and ordered by:

- `DiseaseGrading.display_order`
- `GradingsFeatures.sr_no`

Example:

```json
{
  "disease": {
    "id": 1,
    "name": "Diabetic Retinopathy",
    "gradings": [
      {
        "id": 11,
        "impression": "Mild",
        "display_order": 1,
        "is_active": true,
        "guidelines": "..."
      }
    ]
  }
}
```
