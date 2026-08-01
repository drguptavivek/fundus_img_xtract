# WAI API Statistics API

JSON endpoints for the `/analytics/wai-api-statistics` page. All endpoints require one of:

- `admin`
- `local_admin`
- `data_manager`
- `analytics_viewer`

Rows are scoped by analytics hospital/lab access. Admin users see all rows. Local admins see their hospital. Other non-admin users are limited to their assigned lab units in their hospital.

All endpoints are `GET` and do not require a CSRF token.

## Shared Filters

Supported query parameters:

- `disease_id`: repeatable integer
- `project_id`: repeatable integer
- `ai_model_id`: repeatable integer
- `result_type`: repeatable, one of `positive`, `negative`, `inconclusive`
- `inference_status`: repeatable, one of `success`, `failed`, `running`, `queued`
- `capture_start`: `YYYY-MM-DD`
- `capture_end`: `YYYY-MM-DD`
- `inference_start`: `YYYY-MM-DD`
- `inference_end`: `YYYY-MM-DD`
- `page`: integer, result endpoints only
- `page_size`: integer, result endpoints only, maximum `100`

All data is read from `ai_inference_runs_mv` with `is_latest_for_task_model = true`.

## Options

`GET /api/analytics/wai-api-statistics/options`

Returns filter choices available within the caller's scope.

```json
{
  "diseases": [{"id": 2, "label": "Glaucoma"}],
  "projects": [{"id": 2, "label": "ICMR-VG"}],
  "models": [{"id": 1, "label": "wai_glaucoma_ver1 1"}],
  "result_types": ["positive", "negative", "inconclusive"],
  "inference_statuses": ["success", "failed", "running", "queued"]
}
```

## Summary

`GET /api/analytics/wai-api-statistics/summary`

Returns cards and month-wise counts for the selected filters.

```json
{
  "cards": {
    "images": 120,
    "encounters": 80,
    "positive_images": 12,
    "positive_encounters": 10,
    "failed_runs": 3,
    "inconclusive_runs": 1
  },
  "monthly": [
    {
      "month": "2026-07-01",
      "images": 120,
      "encounters": 80,
      "positive": 12,
      "negative": 105,
      "inconclusive": 1,
      "failed": 3
    }
  ]
}
```

## Image Results

`GET /api/analytics/wai-api-statistics/images`

Returns paginated image-wise latest inference rows.

```json
{
  "rows": [
    {
      "inference_run_id": 564,
      "task_id": 123,
      "disease_name": "Glaucoma",
      "project_title": "ICMR-VG",
      "image_source": "encounter_set_image",
      "image_uuid": "uuid",
      "normalized_capture_date": "2026-07-30",
      "inference_status": "success",
      "result_type": "negative",
      "ai_grade_name": "Normal",
      "ai_probability": 0.0123,
      "thumbnail_url": "/media/encounter-set/image/uuid/thumbnail",
      "viewer_url": "/analytics/encounter/view/123"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total": 120,
    "total_pages": 5
  }
}
```

## Encounter Results

`GET /api/analytics/wai-api-statistics/encounters`

Returns paginated encounter-wise groups. Encounter result is positive if any image is positive, negative if all latest rows are negative, otherwise inconclusive.

```json
{
  "rows": [
    {
      "normalized_patient_encounter_id": 123,
      "patient_identifier": "MRN",
      "project_title": "ICMR-VG",
      "normalized_capture_date": "2026-07-30",
      "latest_inference_at": "2026-07-30T15:30:00+00:00",
      "image_count": 2,
      "run_count": 2,
      "failed_count": 0,
      "encounter_result_type": "negative",
      "image_results": [],
      "viewer_url": "/analytics/encounter/view/123"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total": 80,
    "total_pages": 4
  }
}
```
