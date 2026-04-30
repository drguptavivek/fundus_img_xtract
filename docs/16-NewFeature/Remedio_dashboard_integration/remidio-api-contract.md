# Remidio API Contract

Draft from live probes on 2026-04-30. Detailed observations live in `api_behavior.md`.

Operational setup workflow: `remidio-setup-workflow.md`.

## Auth

Use local, gitignored config:

```env
REMEDIO_BASE_URL=https://remidio-backend-india.appspot.com
REMEDIO_CLIENT_NAME=PACS_GATEWAY
REMEDIO_CLIENT_IDENTIFICATION_TOKEN=...
REMEDIO_EMAIL=...
REMEDIO_PASSWORD=...
```

Probe:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py get-auth-token
```

`POST /api/user/loginUser`

- Headers: `clientName`, `clientIdentificationToken`
- Body: `emailAddress`, `password`
- Success: `data` is the short-lived bearer JWT directly.

`GET /api/gateway/getAuthToken`

- Headers: `Authorization: Bearer <login token>`, `clientName`, `clientIdentificationToken`
- Success: `data` is the long-lived `clientAuthToken` directly.
- Calling again invalidates the previous `clientAuthToken`.

## Common Gateway Headers

```http
clientName: PACS_GATEWAY
clientIdentificationToken: <token>
clientAuthToken: <client auth token>
```

Some calls also include `Authorization: Bearer <login token>`.

## Tested GETs

`GET /api/gateway/getSites`

- Success `data[]`: `siteId`, `siteName`, `siteDomain`
- Tested account does **not** return `siteCustomIdentifier`, even after custom IDs were configured.

Output shape:

```json
{
  "status": {"statusCode": "OK", "message": "HTTP Status - OK"},
  "data": [{"siteId": 0, "siteName": "...", "siteDomain": "..."}],
  "paging": null
}
```

`GET /api/gateway/getQueueItem`

- Empty queue is HTTP `404`.
- Body: `status.statusCode=NOT_FOUND`, message says no items in gateway processing queue.
- Never call `itemSuccessfullyHandled` until local persistence succeeds.

Empty output shape:

```json
{
  "status": {"statusCode": "NOT_FOUND", "message": "No items were found for this organization in the gateway processing queue"},
  "data": "ResourceNotFoundException",
  "paging": null
}
```

`GET /api/gateway/getPatientWithLastExam/{siteIdentifier}/{mrn}`

- Numeric `siteId` from `getSites` worked for the successful test.
- Working tested site: `5504695309172736`
- Custom ID `rpc_comoph_2` returned HTTP `500`, so use numeric `siteId` for this endpoint unless Remidio clarifies otherwise.
- Success `data`: `patientDetails`, `examDetails`, `images`, `creatingUser`
- Image groups include `fopImages`, `aimImages`, `pslImages`, etc.; each has `STANDARD` and `EDITED`.
- Image records include `id`, `localId`, `examId`, `laterality`, `field`, `deviceType`, `path`, `thumbnailPath`, `metadata`, `quality`, dimensions, and quality metrics.

Output shape:

```json
{
  "status": {"statusCode": "OK", "message": "Okay"},
  "data": {
    "patientDetails": {"id": 0, "mrn": "...", "firstName": "...", "dateOfBirth": 0, "gender": "...", "siteId": 0},
    "examDetails": {"id": 0, "localId": "...", "examCustomId": "...", "examDate": 0, "reportDate": 0, "deviceType": ["FOP"], "examState": "ACTIVE"},
    "images": {
      "fopImages": {
        "STANDARD": [{"id": 0, "examId": 0, "laterality": "RIGHT", "field": "MACULA", "deviceType": "FOP", "path": "https://...", "thumbnailPath": "https://..."}],
        "EDITED": []
      }
    },
    "creatingUser": {"userId": 0, "organizationId": 0, "siteId": 0, "roles": ["OPERATOR"]}
  },
  "paging": null
}
```

Not-found output shape:

```json
{
  "status": {"statusCode": "NOT_FOUND", "message": "The patient MRN you're looking for does not exist"},
  "data": "ResourceNotFoundException",
  "paging": null
}
```

`GET /api/gateway/getExamsByDate/{startDate}/{endDate}/{siteCustomId}`

- Dates are `DD-MM-YYYY`.
- Numeric `siteId` failed.
- Visible `siteName` failed.
- This endpoint appears to need true Remidio dashboard `siteCustomIdentifier`.
- Confirmed custom IDs: `rpc_comoph_1`, `rpc_comoph_2`, `rpc_comoph_4`.
- All three returned HTTP `200` with `data: []` for `30-04-2026`.
- For `21-04-2026` to `30-04-2026`, `rpc_comoph_2` returned 6 exams; `rpc_comoph_1` and `rpc_comoph_4` returned empty arrays.
- Non-empty exam records include `patientDetails`, `examDetails`, `images`, `report`, `creatingUser`, `orderingProvider`, and `reportingDoctor`.
- Observed `rpc_comoph_2` records used `deviceType: ["PRISTINE"]`, `pristineImages`, and some records included report objects with `leftEyeDiagnosis`, `rightEyeDiagnosis`, `referRequired`, `imageIds`, and signed report `path`.

Non-empty output shape:

```json
{
  "status": {"statusCode": "OK", "message": "HTTP Status - OK"},
  "data": [
    {
      "patientDetails": {"id": 0, "mrn": "...", "firstName": "...", "dateOfBirth": 0, "gender": "...", "siteId": 0},
      "examDetails": {"id": 0, "localId": "...", "examDate": 0, "reportDate": 0, "deviceType": ["PRISTINE"], "examState": "ACTIVE"},
      "images": {
        "pristineImages": {
          "STANDARD": [{"id": 0, "examId": 0, "laterality": "RIGHT", "deviceType": "PRISTINE", "path": "https://...", "thumbnailPath": "https://..."}],
          "EDITED": []
        }
      },
      "report": {
        "id": 0,
        "examId": 0,
        "patientId": 0,
        "imageIds": [0],
        "leftEyeDiagnosis": "...",
        "rightEyeDiagnosis": "...",
        "referRequired": false,
        "reportDate": 0,
        "reportingDoctorId": 0,
        "path": "https://..."
      },
      "creatingUser": {"userId": 0, "siteId": 0, "roles": ["OPERATOR"]},
      "orderingProvider": {"email": "...", "firstName": "...", "lastName": "..."},
      "reportingDoctor": {"userId": 0, "siteId": 0, "roles": ["DOCTOR"]}
    }
  ],
  "paging": null
}
```

Invalid-site output shape:

```json
{
  "status": {"statusCode": "NOT_FOUND", "message": "The Site Custom ID provided cannot be found for your organisation"},
  "data": "ResourceNotFoundException",
  "paging": null
}
```

## Routing Rules For EyeImageManager

Do not confuse terms:

- Remidio `site` = geographic/screening location.
- EyeImageManager `lab_unit` = operational location.
- EyeImageManager `Area/site` = anatomical site, not Remidio routing.

Minimum routing key:

```text
Remidio account + Remidio site identifier + Remidio deviceType
```

Routes to:

```text
project_id + lab_unit_id + camera_id + base/default disease policy
```

## PDFs And Disease Workflows

- Remidio queue/date APIs may include PDF reports.
- Site/device routing decides project/lab/camera ownership.
- PDF/report parsing should decide additional disease workflows.
- Do not treat one `PatientEncounters.disease_id` as the full disease truth for Remidio sync.

## Local File Persistence

- Metadata pull first stages rows in `remidio_exams`, `remidio_images`, and `remidio_reports`.
- File ingest creates/reuses one `PatientEncounters` row per staged Remidio exam.
- Downloaded images are stored under `IMAGE_DIR/YYYY_MM_DD/` and linked through `EncounterFile`.
- Downloaded PDFs are stored under `PDF_DIR/YYYY_MM_DD/` and linked through `EncounterFilePDF`.
- `remidio_images.encounter_file_id` and `remidio_reports.encounter_file_pdf_id` preserve the source-to-local mapping.
- Default grading tasks are created only when the matched routing rule has `default_disease_id`; null means save files without task creation.
- The downloader accepts absolute signed `http(s)` links only. Plain storage object keys are left staged with a download error.

## Data Validation Rules

Validate every Remidio response before persistence:

- Require top-level `status.statusCode`, `data`, and `paging` keys.
- Treat HTTP `2xx` with non-`OK` `status.statusCode` as an integration error.
- For login/getAuthToken, require `data` to be a JWT-like string.
- For sites, require each site to have numeric `siteId` and non-empty `siteName`.
- For latest-patient success, require `patientDetails.id`, `patientDetails.siteId`, `examDetails.id`, `examDetails.deviceType`, and `images`.
- For each image, require `id`, `examId`, `deviceType`, `path`, `thumbnailPath`, `laterality`, `field`, `width`, and `height`.
- For date-range records, allow `report` to be `null`; if present, validate `id`, `examId`, `patientId`, `imageIds`, `reportDate`, and `path`.
- Validate report `imageIds` against image IDs when possible; unmatched IDs should not block persistence, but should create a reconciliation warning.
- Parse image `metadata` as JSON only if present and valid; otherwise store the raw string and flag parse failure.
- Redact tokens, signed URL query strings, email, MRN, names, DOB, and employee IDs from logs/output snapshots.
- Reject or quarantine records when site/device routing maps to zero or multiple active EyeImageManager rules.
- Do not persist corrected patient identity over Remidio source values; layer corrections separately.

## Error Rules

Safe non-fatal outcomes:

- `404` queue empty.
- `404` MRN not found at site.
- `404` invalid Site Custom ID.

Do not acknowledge queue items after:

- HTTP `500`
- malformed response
- missing file URL
- routing ambiguity
- download or DB persistence failure
