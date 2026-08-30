# Grader Dashboard API

These read-only endpoints power the grader-facing `/grading/` eligibility and history panels. Both endpoints require an authenticated user with the `resident` or `ophthalmologist` application role. Returned records are restricted by the caller's grading/lab scope.

## Get my grading queues

`GET /api/grading/me/queues`

Both dashboard queue panels in one payload. Deliberately asymmetric:
`project_encounter_sets` arrives complete with counts because those are cheap to
derive, while `legacy_diseases` carries **no counts** — each disease is counted
on demand through the per-disease endpoint below, so one large queue cannot hold
up the rest of the dashboard.

Requires the `resident` or `ophthalmologist` role. Results are scoped to the
caller; there is no user parameter.

```json
{
  "success": true,
  "project_encounter_sets": [
    {
      "project": {"id": 3, "title": "Integrated DR Glaucoma Screening", "code": "ICMR-VG"},
      "target": {"key": "disease_encounter:2:15", "label": "DR / EncounterSet",
                 "encounter_set_type_name": "Remidio API Standard Encounter Set"},
      "slots": [
        {"slot": "resident", "label": "Resident", "package_count": 80,
         "task_count": 804, "first_package_uuid": "c20bd587-..."}
      ]
    }
  ],
  "legacy_diseases": [
    {"id": 1, "name": "Glaucoma", "can_grade_resident": true,
     "can_grade_resident2": true, "can_arbitrate": true}
  ]
}
```

## Get one disease queue

`GET /api/grading/me/queues/<disease_id>`

Pending totals and linked follow-ups for a single disease. `combined_pending` is
what the Start Grading control shows, because that control leases either resident
slot. `has_work` is false when the queue is empty in every slot.

Returns `404` with `error.code = "disease_not_gradable"` when the caller holds no
active eligibility for the disease.

```json
{
  "success": true,
  "queue": {
    "disease": {"id": 1, "name": "Glaucoma"},
    "can_grade_resident": true, "can_grade_resident2": true, "can_arbitrate": true,
    "resident_pending": 0, "resident2_pending": 5340, "combined_pending": 5340,
    "arbitration_pending": 0, "arbitration_breakdown": {},
    "linked_followups": [], "linked_followup_total": 0,
    "has_work": true
  }
}
```

### Caching and freshness

Both queue endpoints are served from a Redis object cache with a **30 second**
TTL, keyed per grader (`grading:queue_card:{user}:{disease}` and
`grading:project_queues:{user}`). Pass `?refresh=1` to bypass the cached value
and re-store a freshly computed one; `GET /api/grading/project-encounter-set-queues`
accepts the same parameter.

These counts are a **workload indicator, not an entitlement**. Opening any task
still runs the full per-task eligibility check, so a count that is up to 30
seconds stale cannot grant access to work the grader may not do. Counts are also
coarse in one direction only where a project enforces allocation: they reflect
the exact allocation check, so they do not overstate available work.

Package-state reconciliation runs on every call, including cache hits, because
it is a write that advances packages past their post-Resident2 waiting period.

## Get my grading eligibility

`GET /api/grading/me/eligibility`

The response intentionally separates legacy, non-project permissions from explicit project grader allocations. `role_slots` are workflow slots (`resident`, `resident2`, or `arbitrator`), not application roles. Every project allocation is immediately authoritative; project-owned tasks never fall back to legacy eligibility.

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
