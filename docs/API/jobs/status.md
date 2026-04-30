# Job Status

This surface exposes the list view, job-status JSON, and read-only job pages.

## Routes

- `GET /jobs/`
- `GET /jobs/<job_token>`
- `GET /jobs/<job_token>/view`
- `GET /jobs/results/details/<job_token>`
- `GET /jobs/processing/<job_id>`

## `GET /jobs/`

HTML list of recent jobs.

Auth:
- `@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager", "discrepancy_reviewer", "data_exporter")`

Query params:
- `job_type` optional string
- `page` optional integer, default `1`
- `per_page` optional integer, clamped to `10..100`

Response:
- `200 OK` HTML rendered from `templates/jobs/jobs_list.html`

Template data:
- `jobs`
- `rejections`
- `totals`
- `successes`
- `job_types`
- `selected_job_type`
- `pagination`

## `GET /jobs/<job_token>`

JSON job payload.

Auth:
- same role set as the list page

Response `200`:
```json
{
  "id": 1,
  "token": "abc123",
  "status": "queued",
  "error": null,
  "rejected_summary": null,
  "uploader_user_id": 10,
  "uploader_username": "user",
  "uploader_ip": "127.0.0.1",
  "lab_unit_id": 3,
  "lab_unit_name": "Lab A",
  "lab_unit_hospital_name": "Hospital A",
  "project_id": null,
  "project_title": null,
  "project_code": null,
  "created_at": "2026-04-30T12:00:00Z",
  "updated_at": "2026-04-30T12:00:00Z",
  "items": [],
  "upload_type": "dataset_export"
}
```

Additional fields when `upload_type` is an export:
- `export_files`
- `download_base`

Additional fields for `dataset_export`:
- `dataset_name`
- `dataset_uuid`
- `dataset_detail_url`

Error responses:
- `404 {"error": "job not found"}`

## `GET /jobs/<job_token>/view`

HTML status page.

Response:
- `templates/jobs/export_job_status.html` for export jobs
- `templates/jobs/job_status.html` for all other jobs

## `GET /jobs/results/details/<job_token>`

HTML upload-result page for the original upload job.

## `GET /jobs/processing/<job_id>`

HTML processing page.

## CSRF Rules

- These routes are `GET` only.
- No CSRF token is required.
