# Remidio API Integration

Admin/data-manager API for configuring Remidio accounts and pulling Remidio exam metadata into EyeImageManager.

Auth: Flask login session with role `admin` or `data_manager`.

CSRF: browser/session clients must send the standard `X-CSRFToken` header for `POST`/`PATCH` requests when CSRF protection is enabled.

Scope: Remidio `site` means a Remidio geographic/screening site. EyeImageManager `lab_unit` is the local operational unit. EyeImageManager anatomical site/area is not used for Remidio routing.

## Data Model

Local Remidio tables use integer primary keys.

- `remidio_connections`: encrypted Remidio account credentials and client headers.
- `remidio_sites`: sites returned by `getSites`; `site_custom_identifier` is manually configured because Remidio does not return it.
- `remidio_routing_rules`: maps `connection + site_custom_identifier + remidio_device_type` to `project + lab_unit + camera + optional default_disease`.
- `remidio_exams`: source exam metadata keyed by `connection + remidio_exam_id`.
- `remidio_images`: source image metadata keyed by local `remidio_exam_id + remidio_image_id`; once downloaded, `encounter_file_id` links to the local image file row.
- `remidio_reports`: report/PDF/AI report metadata keyed by local `remidio_exam_id + remidio_report_id + report_type`; once downloaded, `encounter_file_pdf_id` links to the local PDF row.

If `default_disease_id` is null, ingestion stores source metadata only and does not create default grading tasks.

## Endpoints

### List Connections

`GET /api/remidio/connections?project_id=1`

Response:

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "AIIMS Remidio",
      "project_id": 1,
      "base_url": "https://remidio-backend-india.appspot.com",
      "client_name": "PACS_GATEWAY",
      "active": true,
      "site_count": 3
    }
  ]
}
```

### Create Connection

`POST /api/remidio/connections`

```json
{
  "name": "AIIMS Remidio",
  "project_id": 1,
  "base_url": "https://remidio-backend-india.appspot.com",
  "client_name": "PACS_GATEWAY",
  "client_identification_token": "JWT_FROM_REMEDIO",
  "email": "user@example.org",
  "password": "secret"
}
```

Secrets are encrypted before storage and are never returned.

### Update Connection

`PATCH /api/remidio/connections/{connection_id}`

Accepts any create field plus `active`.

### Refresh Token

`POST /api/remidio/connections/{connection_id}/refresh-token`

Logs in with stored email/password, calls `getAuthToken`, and updates token timestamps. Tokens are not persisted or returned.

### Sync Sites

`POST /api/remidio/connections/{connection_id}/sync-sites`

Calls Remidio `GET /api/gateway/getSites` and upserts sites by `connection + remidio_site_id`.

### List Sites

`GET /api/remidio/connections/{connection_id}/sites`

### Configure Site Custom Identifier

`PATCH /api/remidio/sites/{site_id}`

```json
{
  "site_custom_identifier": "rpc_comoph_2",
  "active": true
}
```

The identifier must be copied manually from Remidio dashboard site settings.

### List Routing Rules

`GET /api/remidio/routing-rules?connection_id=1&project_id=1`

### Create Or Update Routing Rule

`POST /api/remidio/routing-rules`

```json
{
  "remidio_connection_id": 1,
  "remidio_site_id": 2,
  "site_custom_identifier": "rpc_comoph_2",
  "remidio_device_type": "FOP",
  "project_id": 1,
  "lab_unit_id": 1,
  "camera_id": 2,
  "default_disease_id": null,
  "active": true
}
```

`remidio_device_type` is normalized to uppercase. Typical values from live testing are `FOP` and `PRISTINE`.

### Pull Exams By Date

`POST /api/remidio/connections/{connection_id}/pull/exams-by-date`

```json
{
  "start_date": "2026-04-01",
  "end_date": "2026-04-30",
  "site_custom_identifier": "rpc_comoph_2",
  "dry_run": false
}
```

Calls Remidio `GET /api/gateway/getExamsByDate/{startDate}/{endDate}/{siteCustomIdentifier}`. Dates may be `YYYY-MM-DD` or `DD-MM-YYYY`; Remidio is called with `DD-MM-YYYY`.

Response:

```json
{
  "success": true,
  "data": {
    "connection_id": 1,
    "dry_run": false,
    "start_date": "01-04-2026",
    "end_date": "30-04-2026",
    "site_custom_identifier": "rpc_comoph_2",
    "summary": {
      "exams_seen": 92,
      "exams_created": 92,
      "exams_updated": 0,
      "images_seen": 564,
      "images_created": 564,
      "images_updated": 0,
      "reports_seen": 26,
      "reports_created": 26,
      "reports_updated": 0
    }
  }
}
```

### Pull Latest Patient Exam

`POST /api/remidio/connections/{connection_id}/pull/latest-patient-exam`

```json
{
  "site_identifier": "5504695309172736",
  "mrn": "17136192",
  "dry_run": false
}
```

Calls Remidio `GET /api/gateway/getPatientWithLastExam/{siteIdentifier}/{mrn}`. Live testing showed this endpoint uses numeric Remidio `siteId`, not the manual `siteCustomIdentifier`.

### Ingest Staged Files

`POST /api/remidio/connections/{connection_id}/ingest/staged-files`

Downloads file bytes for staged Remidio rows and creates normal EyeImageManager rows:

- `PatientEncounters` for each Remidio exam.
- `EncounterFile` for each downloaded image under `IMAGE_DIR/YYYY_MM_DD/`.
- `EncounterFilePDF` for each downloaded PDF/report under `PDF_DIR/YYYY_MM_DD/`.
- Optional `GradingTask` for each downloaded image when the matched routing rule has `default_disease_id`.

Request:

```json
{
  "site_custom_identifier": "rpc_comoph_2",
  "start_date": "2026-04-01",
  "end_date": "2026-04-30",
  "limit": 20,
  "pending_only": true,
  "include_images": true,
  "include_reports": true,
  "create_tasks": true,
  "dry_run": false
}
```

Optional selectors:

- `remidio_exam_row_ids`: local `remidio_exams.id` values.
- `remidio_exam_ids`: external Remidio `examDetails.id` values.

Response:

```json
{
  "success": true,
  "data": {
    "connection_id": 1,
    "dry_run": false,
    "limit": 20,
    "summary": {
      "exams_seen": 2,
      "encounters_created": 2,
      "encounters_reused": 0,
      "images_seen": 8,
      "images_downloaded": 8,
      "images_skipped": 0,
      "reports_seen": 1,
      "reports_downloaded": 1,
      "reports_skipped": 0,
      "tasks_created": 8,
      "tasks_reused": 0,
      "route_errors": 0,
      "download_errors": 0
    }
  }
}
```

The downloader only fetches absolute signed `http(s)` links from Remidio `path`/`downloadUrl` fields. If Remidio returns only a storage object key, the row is left staged with `download_error` instead of guessing an undocumented download endpoint.

## Validation

- Connection name must be unique.
- Connection secrets are required on create and encrypted at rest.
- `site_custom_identifier` is required for date-range pulls and routing rules.
- `remidio_exam_id` is scoped by `remidio_connection_id`.
- `remidio_image_id` and `remidio_report_id` are scoped through the local Remidio exam row.
- Raw Remidio snapshots are stored with obvious tokens, signed URLs, and direct identity fields redacted.

## Current Limits

Queue acknowledgement is not implemented yet. `itemSuccessfullyHandled` should only be added after queue-item metadata and files are durably stored.
