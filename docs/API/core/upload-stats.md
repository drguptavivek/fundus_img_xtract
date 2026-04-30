# Upload Stats API

These routes return cached, hospital-scoped upload metrics for the current user.

Auth and CSRF:

- `GET` only, so no CSRF is required.
- Roles required: `admin`, `local_admin`, `fileUploader`, `optometrist`, `data_manager`.

## Routes

| Route | Method | Auth | Response | Status codes |
| --- | --- | --- | --- | --- |
| `/api/upload-stats/today` | `GET` | Session + login + role set above | `{ "success": true, "data": object, "timestamp": str }` | `403` on role failure. |
| `/api/upload-stats/last-7-days` | `GET` | Session + login + role set above | `{ "success": true, "data": object, "timestamp": str }` | `403` on role failure. |

## Shared `data` shape

```json
{
  "timezone": "UTC",
  "matrix": {
    "mine": {
      "today": { "zip": 0, "direct": 0, "pregraded": 0 },
      "cumulative": { "zip": 0, "direct": 0, "pregraded": 0 }
    },
    "total": {
      "today": { "zip": 0, "direct": 0, "pregraded": 0 },
      "cumulative": { "zip": 0, "direct": 0, "pregraded": 0 }
    }
  },
  "zip_daily": {
    "my": [
      {
        "date": "2026-04-30",
        "attempted": 0,
        "success": 0,
        "images_processed": 0,
        "dr_pdfs": 0,
        "glaucoma_pdfs": 0,
        "no_ai_reports": 0,
        "encounter_capture_date_min": null,
        "encounter_capture_date_max": null
      }
    ],
    "all": []
  },
  "direct_pregraded_by_disease": {
    "range": "today",
    "my": [
      { "disease_id": 1, "disease_name": "DR", "direct_count": 0, "pregraded_count": 0 }
    ],
    "all": []
  }
}
```

## Notes

- `today` uses the caller’s timezone, falling back to `DEFAULT_DISPLAY_TIMEZONE`, then `TIMEZONE`, then UTC.
- The route is cache-backed with different TTLs for the daily and 7-day variants.
- The data is scoped to the caller’s hospital lab units only.
