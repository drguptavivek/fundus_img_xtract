# Grader Dashboard API

These read-only endpoints power the grader-facing `/grading/` eligibility and history panels. Both endpoints require an authenticated user with the `resident` or `ophthalmologist` application role. Returned records are restricted by the caller's grading/lab scope.

## Get my grading eligibility

`GET /api/grading/me/eligibility`

The response intentionally separates legacy, non-project permissions from explicit project grader allocations. `role_slots` are workflow slots (`resident`, `resident2`, or `arbitrator`), not application roles. A project allocation with `effective: false` is configured but is not active because project allocation enforcement is disabled.

```json
{
  "success": true,
  "eligibility": {
    "non_project": [
      {
        "hospital": {"id": 1, "name": "Hospital"},
        "lab_unit": {"id": 2, "name": "Retina"},
        "disease": {"id": 3, "name": "DR"},
        "role_slots": ["resident"]
      }
    ],
    "project": [
      {
        "project": {"id": 4, "title": "Screening", "code": "SCR"},
        "lab_unit": {"id": 2, "name": "Retina"},
        "scope": "disease_encounter",
        "capacity": "resident2",
        "disease": {"id": 3, "name": "DR"},
        "encounter_set_type": null,
        "enforcement_enabled": true,
        "effective": true
      }
    ]
  }
}
```

## Get my grading history

`GET /api/grading/me/history`

Query parameters:

- `date`: optional local grading date in `YYYY-MM-DD`. Today is used initially; when that date has no matching records, the latest active grading day is returned.
- `type`: `all` (default), `image`, or `encounter_set`.
- `disease_id`: optional disease filter.
- `page`: positive page number; default `1`.
- `per_page`: records per page; default `12`, maximum `50`.

The response contains daily totals, previous/next active grading dates, the last seven active grading sessions, filter options, and history cards. An immutable EncounterSet submission is returned as one card containing its set-level result and associated image observations. Standalone image grades remain individual cards. The daily `total_tasks` counts grading observations while `total_images` counts unique physical image UUIDs.

```json
{
  "success": true,
  "history": {
    "selected_date": "2026-08-09",
    "requested_date": null,
    "used_latest_fallback": true,
    "history_type": "all",
    "disease_id": null,
    "page": 1,
    "per_page": 12,
    "total_cards": 2,
    "total_pages": 1,
    "total_tasks": 5,
    "total_images": 3,
    "previous_date": "2026-08-07",
    "next_date": null,
    "available_diseases": [{"id": 3, "name": "DR"}],
    "trends": [{"date": "2026-08-09", "task_count": 5, "image_count": 3}],
    "items": []
  }
}
```

Invalid dates or filter values return HTTP `400`:

```json
{
  "success": false,
  "error": {
    "code": "invalid_history_filter",
    "message": "Date must use YYYY-MM-DD format."
  }
}
```

Both routes are safe `GET` requests and do not require a CSRF token. The `/grading/` page uses the same DTO service and refreshes only the history panel for HTMX filter and pagination requests.
