# ai_inference_runs_mv

`ai_inference_runs_mv` normalizes AI API inference runs for reporting and UI pagination. It keeps one row per `ai_inference_runs` row, adds image/encounter/project/disease context, and derives compact result fields for Wadhwani AI statistics.

## Purpose

- Browse AI API run history without joining large source tables at request time.
- Filter by disease, project, capture date, inference date, AI model, run status, and result type.
- Count latest image-wise and encounter-wise inference outcomes in PostgreSQL.
- Preserve failed and running API runs that do not create AI grades.

## Key Fields

- Run identity: `inference_run_id`, `task_id`, `task_uuid`, `ai_model_id`, `integration_id`
- Run status: `inference_status`, `http_status`, `error_code`, `error_message`, `retry_count`
- Timing: `inference_created_at`, `inference_started_at`, `inference_finished_at`, `inference_updated_at`
- Model: `ai_model_name`, `ai_model_version`, `integration_provider`
- API result: `prediction_id`, `api_prediction`, `api_predicted_class`, `api_predicted_class_name`, `result_json`
- Derived result: `result_type` (`positive`, `negative`, `inconclusive`, or `NULL` for non-success runs)
- Latest flag: `is_latest_for_task_model`
- AI grade context: `ai_grade_id`, `ai_grade_name`, `ai_probability`, `ai_review_status`
- Source context: `image_source`, `image_uuid`, `image_filename`, `normalized_patient_encounter_id`
- Filters: `disease_id`, `disease_name`, `project_id`, `project_title`, `normalized_capture_date`

## Notes

Successful Wadhwani API runs create `grades.role_slot = 'ai'`, which continue to appear in the existing image v2 and encounter pivot materialized views. This view keeps the API-run layer separate so failures, running jobs, API payloads, and inference timestamps remain queryable.

## Refresh

The regular materialized-view scheduler refreshes this view after `mvw_image_listing_all`.

Manual refresh:

```sql
REFRESH MATERIALIZED VIEW ai_inference_runs_mv;
```
