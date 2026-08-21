# Remidio API Behavior Notes

This document records Remidio Host Gateway API behavior observed from local probes and from the supplied Remidio mail/Postman collection.

## Sources

- Live probe script: `scripts/probe_remedio_api.py`
- Local token cache: `token.toml` (gitignored)
- Sanitized probe outputs: `docs/16-NewFeature/Remedio_dashboard_integration/probe_outputs/` (gitignored)
- Cleaned Remidio mail: `docs/16-NewFeature/Remedio_dashboard_integration/mail_text.md`
- Supplied Postman collection: `postman_remedio.json` (gitignored because it contains sample tokens)

## Safety Rules

- Do not commit Remidio credentials, bearer tokens, client auth tokens, or signed file URLs.
- `getQueueItem` must not be paired with `itemSuccessfullyHandled` until the item has been fully persisted locally.
- For discovery, prefer read-only calls such as `login`, `getAuthToken`, `getSites`, and date-based exam lookup.
- The probe script sanitizes tokens and signed URL query strings before writing JSON output.

## Credentials And Local Setup

Store login/config values in gitignored `develop.config.env`:

```env
REMEDIO_BASE_URL=https://remidio-backend-india.appspot.com
REMEDIO_CLIENT_NAME=PACS_GATEWAY
REMEDIO_CLIENT_IDENTIFICATION_TOKEN=...
REMEDIO_EMAIL=...
REMEDIO_PASSWORD=...
```

Generate or refresh local tokens:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py get-auth-token
```

This writes `token.toml` with a short-lived bearer token and a `client_auth_token`. `token.toml` is gitignored.

## Common Response Envelope

Observed successful responses use this top-level shape:

```json
{
  "status": {
    "statusCode": "OK",
    "message": "HTTP Status - OK"
  },
  "data": {},
  "paging": null
}
```

`data` may be an object, array, or token string depending on endpoint.

## Headers

All gateway calls require:

```http
clientName: PACS_GATEWAY
clientIdentificationToken: <client identification token>
```

Gateway data calls also require:

```http
clientAuthToken: <client auth token>
```

`getAuthToken` requires the short-lived login bearer token:

```http
Authorization: Bearer <login access token>
```

## Tested Endpoints

### Login

```http
POST /api/user/loginUser
```

Request body:

```json
{
  "emailAddress": "user@example.com",
  "password": "..."
}
```

Observed response on 2026-04-30:

```json
{
  "status": {
    "statusCode": "OK",
    "message": "HTTP Status - OK"
  },
  "data": "<jwt bearer token>",
  "paging": null
}
```

Important behavior:

- The login bearer token is returned directly as `data`, not as `data.accessToken`.
- The mail says this token is short-lived and expires after about 15 minutes of inactivity.

Probe command:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py login
```

### Get Client Auth Token

```http
GET /api/gateway/getAuthToken
```

Required headers:

```http
Authorization: Bearer <login bearer token>
clientName: PACS_GATEWAY
clientIdentificationToken: <client identification token>
```

Observed response on 2026-04-30:

```json
{
  "status": {
    "statusCode": "OK",
    "message": "HTTP Status - Okay"
  },
  "data": "<jwt client auth token>",
  "paging": null
}
```

Important behavior:

- The `clientAuthToken` is returned directly as `data`.
- The mail describes this token as long-lived and near-permanent.
- Calling this endpoint again invalidates the previously generated `clientAuthToken`.

Probe command:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py get-auth-token
```

### Get Sites

```http
GET /api/gateway/getSites
```

Required headers:

```http
clientName: PACS_GATEWAY
clientIdentificationToken: <client identification token>
clientAuthToken: <client auth token>
```

Observed response on 2026-04-30:

```json
{
  "status": {
    "statusCode": "OK",
    "message": "HTTP Status - OK"
  },
  "data": [
    {
      "siteId": 4678934377529344,
      "siteName": "AIIMS-Delhi",
      "siteDomain": "gmail.com"
    }
  ],
  "paging": null
}
```

Observed site fields:

- `siteId`
- `siteName`
- `siteDomain`

Note: the Remidio mail says Custom IDs are returned by Get Sites and are needed for date-based/latest-exam APIs. The tested response did not include `siteCustomIdentifier`, even after custom IDs were configured in the dashboard.

Probe command:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py get-sites
```

### Get Element From Queue

```http
GET /api/gateway/getQueueItem
```

Required headers:

```http
clientName: PACS_GATEWAY
clientIdentificationToken: <client identification token>
clientAuthToken: <client auth token>
```

Observed queue-empty response on 2026-04-30:

```json
{
  "status": {
    "statusCode": "NOT_FOUND",
    "message": "No items were found for this organization in the gateway processing queue"
  },
  "data": "ResourceNotFoundException",
  "paging": null
}
```

Important behavior:

- Remidio returns HTTP `404` when the queue is empty.
- This matches the Remidio mail guidance.
- The probe command `queue-peek` does not acknowledge the item.
- Do not call `itemSuccessfullyHandled` until local persistence succeeds.

Postman image example for a non-empty queue includes:

- `data.type`
- `data.image`
- `data.exam`
- `data.patient`
- `data.creatingUser`
- `data.site`

Probe command:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py queue-peek
```

### Get Patient Visits By Date

```http
GET /api/gateway/getExamsByDate/{startDate}/{endDate}/{siteCustomId}
```

Purpose:

- Returns exams for visits between `startDate` and `endDate`, inclusive.
- Dates must use `DD-MM-YYYY`.
- Remidio mail says each exam object includes images, reports, patient information, and exam information.

Observed behavior on 2026-04-30:

- Passing numeric `siteId` from `getSites` returned HTTP `404`.
- Passing visible `siteName` from `getSites` returned HTTP `404`.
- Error message for both: `The Site Custom ID provided cannot be found for your organisation`.
- Passing configured custom IDs `rpc_comoph_1`, `rpc_comoph_2`, and `rpc_comoph_4` returned HTTP `200` with `data: []` for `30-04-2026`.
- For `21-04-2026` through `30-04-2026`, `rpc_comoph_2` returned 6 exam records, while `rpc_comoph_1` and `rpc_comoph_4` returned empty arrays.
- The non-empty `rpc_comoph_2` response included top-level record keys: `patientDetails`, `examDetails`, `images`, `report`, `creatingUser`, `orderingProvider`, and `reportingDoctor`.
- Observed device type was `PRISTINE`; image records were under `images.pristineImages`.
- Four of six records had a `report` object with keys including `imageIds`, `leftEyeDiagnosis`, `rightEyeDiagnosis`, `referRequired`, `reportDate`, and signed report `path`; two had `report: null`.

Conclusion:

- `siteCustomId` is a separate Remidio dashboard setting.
- It is not the numeric `siteId`.
- It is not necessarily the visible `siteName`.
- The tested account's `getSites` response did not include `siteCustomIdentifier`, so custom IDs must be tracked locally or obtained from the Remidio dashboard/service engineer.

Probe command:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py visits-by-date \
  --start-date 30-04-2026 \
  --end-date 30-04-2026 \
  --site-custom-id <siteCustomId>
```

## Untested / Partially Documented Endpoints

These endpoints are documented in the Remidio mail/Postman collection but still need live probe outputs.

### Element Handled Successfully

```http
POST /api/gateway/itemSuccessfullyHandled
```

Purpose:

- Removes the current item from Remidio's download queue after local handling succeeds.

Safety:

- Once acknowledged, the item is never added to the queue again.
- This endpoint should not be used in discovery scripts.

### Get Latest Patient Exam

```http
GET /api/gateway/getPatientWithLastExam/{siteCustomId}/{mrn}
```

Purpose:

- Returns the most recent exam for a patient at a given Remidio site custom ID.
- Alternative to the queue flow.

Required headers used in probe:

```http
Authorization: Bearer <login bearer token>
clientName: PACS_GATEWAY
clientIdentificationToken: <client identification token>
clientAuthToken: <client auth token>
```

Observed behavior on 2026-04-30:

- Passing visible site name `AIIMS-Delhi` returned HTTP `500` with plain body `Something went wrong! Please try again later`.
- Passing numeric `siteId` values from `getSites` returned structured behavior:
  - `4678934377529344`: HTTP `404`, patient MRN not found.
  - `5504695309172736`: HTTP `200`, latest exam returned.
  - `6405634341732352`: HTTP `404`, patient MRN not found.

This differs from `getExamsByDate`, where numeric `siteId` was rejected as an invalid Site Custom ID. For latest-patient lookup, numeric `siteId` appears to be accepted by the API even though the path variable is named `siteCustomId` in the Postman collection.

Re-confirmed on 2026-08-21 through the application's own stored connection credentials
(connection `Comoph`, site `comoph_4834` / `5733647311175680`):

- Site custom identifier `comoph_4834`: HTTP `404`.
- Numeric site id `5733647311175680`: HTTP `200`, 1 exam / 4 images / 3 reports.

Two confirmations four months apart, so this is stable behaviour rather than a
transient. `pull_latest_patient_exam` therefore passes the numeric id and resolves the
custom identifier locally for storage.

Observed successful response shape:

```json
{
  "status": {
    "statusCode": "OK",
    "message": "Okay"
  },
  "data": {
    "patientDetails": {
      "id": 0,
      "mrn": "<redacted>",
      "firstName": "<redacted>",
      "dateOfBirth": "<redacted>",
      "gender": "FEMALE",
      "siteId": 5504695309172736
    },
    "examDetails": {
      "id": 4745599345754112,
      "localId": "REM-2255::1776666256",
      "examCustomId": "17",
      "examDate": 1776666256640,
      "reportDate": 0,
      "deviceType": ["FOP"],
      "examState": "ACTIVE"
    },
    "images": {
      "fopImages": {
        "STANDARD": [
          {
            "id": 6043389145382912,
            "examId": 4745599345754112,
            "localId": "1776666290",
            "laterality": "RIGHT",
            "field": "MACULA",
            "deviceType": "FOP",
            "quality": "SUFFICIENT",
            "isCropped": true,
            "width": 2866,
            "height": 2866,
            "path": "https://storage.googleapis.com/...?[signed-query]",
            "thumbnailPath": "https://storage.googleapis.com/...?[signed-query]",
            "metadata": "{...}",
            "discQualityResults": {
              "acceptableQuality": true,
              "discPresent": true,
              "qualityScore": 1.0,
              "roiX": 0.6933594,
              "roiY": 0.6171875
            }
          }
        ],
        "EDITED": []
      }
    },
    "creatingUser": {
      "userId": 4813320817213440,
      "organizationId": 5545378933899264,
      "siteId": 5504695309172736,
      "roles": ["OPERATOR", "ADMIN", "DOCTOR"]
    }
  },
  "paging": null
}
```

Observed image grouping keys:

- `aimImages`
- `fopImages`
- `instaKCImages`
- `instaZImages`
- `obmImages`
- `otherImages`
- `pristine1Point5Images`
- `pristineImages`
- `pslImages`

Each group has `STANDARD` and `EDITED` arrays.

Probe command:

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_remedio_api.py latest-patient-exam \
  --site-custom-id <siteCustomId> \
  --mrn <mrn>
```

### Create Patient Exam

```http
POST /api/gateway/createPatientExam
```

Purpose:

- Registers a patient and schedules an exam in Remidio.
- If the MRN already exists, Remidio schedules a new exam for the existing patient.

### Audit Logs

```http
POST /api/logger/single
POST /api/logger/batch
```

Purpose:

- Optional Remidio-side logging for integration troubleshooting.

## EyeImageManager Mapping Implications

Remidio vocabulary differs from EyeImageManager vocabulary:

- Remidio `site` means a geographic or screening location.
- EyeImageManager `lab_unit` is our local operational location concept.
- EyeImageManager `Area` or UI "site" means anatomical site and must not be used for Remidio geographic routing.

Minimum routing inputs expected for integration:

```text
Remidio account
+ Remidio geographic site identifier/name/custom identifier
+ Remidio device type
-> EyeImageManager project_id
-> EyeImageManager lab_unit_id
-> EyeImageManager camera_id
-> base/default disease policy
```

PDF/report handling must be separate from routing:

- Remidio queue items may include PDF reports.
- Date-based exam lookup may include generated reports.
- PDF/report content may determine additional disease workflows for the same encounter/images.
