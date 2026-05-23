# Remidio API Integration

Admin/data-manager API for configuring Remidio accounts and pulling Remidio exam metadata into EyeImageManager.

Auth: Flask login session with role `admin` or `data_manager`.

CSRF: browser/session clients must send the standard `X-CSRFToken` header for `POST`/`PATCH` requests when CSRF protection is enabled.

Scope: Remidio `site` means a Remidio geographic/screening site. EyeImageManager `lab_unit` is the local operational unit. EyeImageManager anatomical site/area is not used for Remidio routing.

## Data Model

Local Remidio tables use integer primary keys.

- `remidio_connections`: encrypted Remidio account credentials and client headers.
- `remidio_sites`: sites returned by `getSites`; `site_custom_identifier` is manually configured because Remidio does not return it.
- `remidio_api_source_rules`: Remidio API source selectors keyed by `connection + site_custom_identifier + remidio_device_type`.
- `project_upload_profile_remidio_api_bindings`: date-windowed bindings from one API source rule to one enabled project upload profile, lab unit, and camera.
- `remidio_routing_rules`: legacy direct Remidio API routing table retained for compatibility. It is not used by the new EncounterSet upload-profile workflow.
- `remidio_exams`: source exam metadata keyed by `connection + remidio_exam_id`.
- `remidio_images`: source image metadata keyed by local `remidio_exam_id + remidio_image_id`; once downloaded through the new workflow, `encounter_set_image_id` links to the local EncounterSet image row.
- `remidio_reports`: report/PDF/AI report metadata keyed by local `remidio_exam_id + remidio_report_id + report_type`; once downloaded through the new workflow, `encounter_set_attachment_id` links to the local non-task attachment row.
- `remidio_api_exam_encounters`: duplicate-safe association from one staged Remidio exam to one routed EncounterSet.

Remidio ZIP uploads remain separate. ZIP task defaults are configured on Upload & Grading Profiles with `default_disease_ids` and are not controlled by Remidio API source rules.

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

### Legacy Routing Rules

These endpoints are retained for compatibility with the older direct Remidio API ingestion design. New Remidio API routed EncounterSet workflows should use API Source Rules plus API Bindings below.

`GET /api/remidio/routing-rules?connection_id=1&project_id=1`

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

### List API Source Rules

`GET /api/remidio/api-source-rules?connection_id=1`

Response rows include active project/profile bindings for display:

```json
{
  "success": true,
  "data": [
    {
      "id": 4,
      "remidio_connection_id": 1,
      "connection_name": "r.pcenter",
      "site_custom_identifier": "rpc_comoph_2",
      "remidio_device_type": "PRISTINE",
      "active": true,
      "bindings": []
    }
  ]
}
```

### Create Or Update API Source Rule

`POST /api/remidio/api-source-rules`

```json
{
  "id": 4,
  "remidio_connection_id": 1,
  "remidio_site_id": 2,
  "site_custom_identifier": "rpc_comoph_2",
  "remidio_device_type": "PRISTINE",
  "active": true
}
```

An active source rule is unique by connection, site custom identifier, and device type.

### List API Bindings

`GET /api/remidio/api-bindings?project_upload_profile_id=7&source_rule_id=4`

### Create Or Update API Binding

`POST /api/remidio/api-bindings`

```json
{
  "project_upload_profile_id": 7,
  "remidio_api_source_rule_id": 4,
  "lab_unit_id": 2,
  "camera_id": 8,
  "active_from_date": "2026-04-01",
  "active_to_date": null,
  "active": true
}
```

Binding validation requires:

- the target project-profile mapping is active
- the Upload Profile is marked `automated_remidio_populated`
- the Upload Profile allows only `encounter_set`
- the Upload Profile includes the seeded `remidio_api_standard` EncounterSetType
- the Remidio EncounterSet mapping has image grading schemes and one default image grading scheme
- the lab unit is within the caller's management scope
- active date windows do not overlap for the same API source rule

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
- `EncounterSetImage` for each downloaded clinical image under `files/encounter_sets/YYYY_MM_DD/<encounter_id>/`.
- `EncounterSetAttachment` for each downloaded report/PDF under `files/encounter_sets/YYYY_MM_DD/<encounter_id>/attachments/`.
- `PatientEncounterTargetDisease` rows for image and encounter grading schemes configured on the routed Upload Profile.

The new workflow does not create grading tasks at Remidio API fetch time. Task creation remains a later verification/finalization step so documents, reports, discarded encounters, and non-gradable images do not leak into grading.

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
      "tasks_created": 0,
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
- New Remidio API source rules are unique by active `connection + site_custom_identifier + remidio_device_type`.
- New Remidio API project/profile bindings cannot overlap by date for the same API source.
- `remidio_exam_id` is scoped by `remidio_connection_id`.
- `remidio_image_id` and `remidio_report_id` are scoped through the local Remidio exam row.
- Raw Remidio snapshots preserve source identity, clinical text, and signed/source URL fields for controlled DB storage. Credential-like fields such as auth tokens, passwords, and JWTs are still redacted.

## Current Limits

Queue acknowledgement is not implemented yet. `itemSuccessfullyHandled` should only be added after queue-item metadata and files are durably stored.
