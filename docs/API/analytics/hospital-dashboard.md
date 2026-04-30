# Hospital Dashboard

This surface powers the hospital dashboard charts and summaries.

## Routes

- `GET /analytics/hospital-dashboard`
- `GET /analytics/api/hospital-dashboard/disease-view`
- `GET /analytics/api/hospital-dashboard/lab-disease-view`
- `GET /analytics/api/hospital-dashboard/user-view`
- `GET /analytics/api/hospital-dashboard/roster-view`
- `GET /analytics/api/hospital-dashboard/encounter-view`

## Shared auth and scoping

Auth:
- `@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")`

All JSON endpoints are scoped to the current user’s lab units.
If the user has no scoped lab units, the JSON endpoints return empty data with `lab_unit_scope_count: 0`.

## `GET /analytics/hospital-dashboard`

HTML page.

Response:
- `200 OK` HTML rendered from `templates/analytics/hospital_dashboard.html`

The page receives:
- `hospitals`
- `lab_units`
- `diseases`
- `lab_unit_scope_count`

## `GET /analytics/api/hospital-dashboard/disease-view`

Response `200`:
```json
{
  "data": [
    {
      "disease_id": 1,
      "disease_name": "DR",
      "total_tasks": 0,
      "pending_resident": 0,
      "pending_resident_pct": 0,
      "pending_resident2": 0,
      "pending_resident2_pct": 0,
      "pending_arbitration": 0,
      "pending_arbitration_pct": 0,
      "non_gradable_count": 0,
      "non_gradable_pct": 0
    }
  ],
  "meta": {
    "lab_unit_scope_count": 0,
    "cumulative_total_tasks": 0,
    "cumulative_non_gradable_count": 0,
    "cumulative_non_gradable_pct": 0,
    "filters": {
      "disease_id": null,
      "lab_unit_id": null,
      "hospital_id": null
    }
  }
}
```

## `GET /analytics/api/hospital-dashboard/lab-disease-view`

Same envelope as `disease-view`, but each `data[]` row also includes:
- `hospital_id`
- `hospital_name`
- `lab_unit_id`
- `lab_unit_name`

## `GET /analytics/api/hospital-dashboard/user-view`

Response `200`:
```json
{
  "data": [
    {
      "disease_id": 1,
      "disease_name": "DR",
      "user_id": 12,
      "user_name": "User Name",
      "completed_count": 0
    }
  ],
  "meta": {
    "lab_unit_scope_count": 0,
    "filters": {
      "disease_id": null,
      "lab_unit_id": null,
      "hospital_id": null
    }
  }
}
```

## `GET /analytics/api/hospital-dashboard/roster-view`

Response `200`:
```json
{
  "data": [
    {
      "hospital_id": 1,
      "hospital_name": "Hospital A",
      "lab_unit_id": 2,
      "lab_unit_name": "Lab A",
      "disease_id": 3,
      "disease_name": "AMD",
      "resident_slot_users": [],
      "resident2_slot_users": [],
      "arbitrator_slot_users": []
    }
  ],
  "meta": {
    "lab_unit_scope_count": 0,
    "filters": {
      "disease_id": null,
      "lab_unit_id": null,
      "hospital_id": null
    }
  }
}
```

## `GET /analytics/api/hospital-dashboard/encounter-view`

Response `200`:
```json
{
  "data": {
    "total_encounters": 0,
    "verified_encounters": 0,
    "verified_encounter_pct": 0,
    "pending_direct_images": 0,
    "ai_grades_by_disease": [
      {
        "disease_id": 1,
        "disease_name": "DR",
        "ai_grade_count": 0
      }
    ]
  },
  "meta": {
    "lab_unit_scope_count": 0,
    "filters": {
      "disease_id": null,
      "lab_unit_id": null,
      "hospital_id": null
    }
  }
}
```

## Query params

All JSON endpoints accept the same optional filters:
- `disease_id`
- `lab_unit_id`
- `hospital_id`

## Error handling

- The roster endpoint returns `500` with `{"data":[],"error":"Failed to fetch roster view: ..."}`
- Other endpoints return empty data when no scoped lab units exist rather than an error
