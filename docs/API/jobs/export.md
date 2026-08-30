# Job Export

This surface covers export regeneration for dataset and discrepancy jobs.

## Route

- `POST /jobs/<job_token>/regenerate`

Auth:
- `@roles_required("admin", "local_admin", "data_manager", "discrepancy_reviewer", "data_exporter", "dataset_creator")`

Rate limit:
- `1 per minute`

CSRF:
- Required

Behavior:
- Only jobs with `upload_type` `dataset_export` or `discrepancy_export` are accepted
- Export jobs are owner/admin only at the job boundary, including historical rows with a Lab Unit
- Dataset exports require the dataset to still exist, be active, finalized, and contain selected tasks
- Discrepancy exports are rebuilt from the stored `filters.json`
- Generated Excel rows include grade timestamp columns for `resident_grade`, `resident2_grade`, `arbitrator_grade`, `review_grade`, `regrade_adj_grade`, and `ai_grade`. Timestamp columns use ISO 8601 strings and are named with the `_date` suffix, for example `resident_grade_date`.

Success response:
- `302` redirect back to the job status page
- Flash message indicates the queued export type

Common failure cases:
- `404` if the job is not an export job or is outside the caller’s scope
- `302` redirect with flash if the dataset is missing, inactive, not finalized, or has no exportable tasks

## CSRF Rules

- This is a mutating form POST and must include `{{ csrf_field() }}` or `X-CSRFToken` if submitted from JS.
