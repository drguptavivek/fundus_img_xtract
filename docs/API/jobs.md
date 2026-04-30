# Job APIs

These endpoints expose job status and export regeneration controls.

## `GET /jobs/<job_token>`

Returns the JSON payload for one job.

Response fields:
- `job_id`
- `job_token`
- `job_status`
- `items`
- `upload_type`
- `export_files` when the job is a discrepancy or dataset export
- `download_base` when export files are present
- `dataset_name`, `dataset_uuid`, and `dataset_detail_url` for dataset export jobs

## `GET /jobs/<job_token>/view`

Returns the HTML status page for the job.

## `POST /jobs/<job_token>/regenerate`

Requeues export jobs.

Auth:
- `admin`, `local_admin`, `data_manager`, `discrepancy_reviewer`, `data_exporter`, `dataset_creator`

Common errors:
- job not found
- not an export job
- dataset not finalized for dataset exports

## Legacy HTML helpers

- `GET /jobs/<job_token>/view` renders HTML, not JSON
- `GET /jobs/results/details/<job_token>` renders HTML, not JSON
- `GET /jobs/processing/<job_id>` renders HTML, not JSON
