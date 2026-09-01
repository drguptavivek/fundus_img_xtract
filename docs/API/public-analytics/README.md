# Public KPI API

## `GET /api/public_kpis`

Returns privacy-safe, system-wide aggregate counts for the public homepage,
HTMX interfaces, JavaScript clients, and mobile applications.

- Authentication: none; this exact path is public in the root application guard.
- Authorization scope: system-wide aggregate counts only.
- CSRF: not required for this read-only `GET` request.
- Cache: responses are computed at most once every 300 seconds per application cache.
- Patient, hospital, lab, user, and project-level identifying details are never returned.

### JSON response

JSON is returned by default.

```json
{
  "success": true,
  "data": {
    "total_images": 30,
    "zip_images": 10,
    "direct_images": 8,
    "encounter_set_images": 12,
    "total_encounters": 9,
    "zip_encounters": 4,
    "encounter_set_encounters": 5,
    "total_ai_gradings": 6,
    "total_gradings": 18,
    "active_projects": 3,
    "total_tasks": 21,
    "disease_task_counts": {
      "DR": 11,
      "Glaucoma": 7
    },
    "generated_at": "2026-09-01T08:00:00+00:00"
  },
  "meta": {
    "cache_ttl_seconds": 300
  }
}
```

Count definitions:

- `total_images`: physical ZIP encounter images, direct-upload images, and EncounterSet images.
- `total_encounters`: ZIP-backed patient encounters plus set-based EncounterSets. Direct image uploads are not encounters.
- `total_ai_gradings`: rows whose grading role is `ai`.
- `total_gradings`: all human and AI grade rows.
- `active_projects`: projects whose `active` flag is true.
- `total_tasks`: all grading tasks, including image, encounter, and unified targets.
- `disease_task_counts`: image-backed tasks grouped by disease. Patient-encounter targets and unified EncounterSet scopes are excluded.

### HTMX response

Send `HX-Request: true` to receive the shared HTML KPI-card fragment instead
of JSON. The public homepage and `/analytics` use this response mode.

```bash
curl -H 'HX-Request: true' https://eyeimg.aiims.edu.in/api/public_kpis
```

### Errors

Unexpected database or cache failures return the application's standard JSON
`500` response. Clients should retain their loading/error state and retry later.
