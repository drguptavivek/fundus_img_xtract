# IITK/AIIMS Image Capture API Contract

This document captures the upstream contract supplied in
`iitk-api/ANNOTATION_API_BRIEF.pdf` and
`iitk-api/ANNOTATION_LABEL_SCHEMA.pdf`, plus sanitized observations from the
read-only local probe. The source PDFs are local reference files and are not
committed.

## Safety and local configuration

- Base URL: `https://asia-south1-imagecapture-6b306.cloudfunctions.net`
- Region: `asia-south1` (Mumbai)
- Authentication: `Authorization: Bearer <IITK_TOKEN>`
- The token is supplied out of band and must not be committed, logged, printed,
  or included in probe output.
- The current discovery workflow calls only the three documented GET endpoints.
  It never calls `POST /annotations`.
- The provider requests a rate of approximately 60 requests per minute or less.

The supplied contract does not define a retry policy or `Retry-After`
behavior, so the local integration uses the conservative single-retry policy
documented below.

For local probing, add the token to the gitignored `develop.config.env`:

```env
IITK_TOKEN=...
```

The probe loads the file without overriding an already exported environment
variable. `IITK_BASE_URL` or `--base-url` may override the URL for isolated
testing. To prevent bearer-token disclosure, overrides must use HTTPS; plain
HTTP is accepted only for a localhost test server.

## Read endpoints

### `GET /listSessions`

Returns capture-session metadata without image bytes.

Optional query parameters:

| Parameter | Contract |
|---|---|
| `site` | Site identifier filter |
| `from` | ISO date applied to `startedAt` |
| `to` | ISO date applied to `startedAt` |
| `status` | `complete` or `partial` |
| `limit` | Default 100, maximum 200 |
| `pageToken` | Opaque value returned as `nextPageToken` |

Documented response shape:

```json
{
  "sessions": [
    {
      "sessionId": "uuid",
      "site": "site-slug",
      "mode": "closeup",
      "startedAt": "2026-07-21T12:43:38.030Z",
      "capturedPositions": ["primary", "up"],
      "expectedPositions": 9,
      "status": "complete",
      "imageCount": 10,
      "mrn": "redacted",
      "age": 34,
      "eye": "ou",
      "gender": "male",
      "diagnosis": "other",
      "diagnosisOther": "redacted"
    }
  ],
  "nextPageToken": "opaque-or-null"
}
```

When `nextPageToken` is non-null, pass it back as `pageToken` without decoding
or modifying it.

### `GET /listImages`

Required query parameter: `sessionId` from `/listSessions`.

Documented response shape:

```json
{
  "sessionId": "uuid",
  "mode": "closeup",
  "images": [
    {
      "filename": "redacted.jpg",
      "position": "primary",
      "sizeBytes": 2116695,
      "contentType": "image/jpeg",
      "capturedAt": "2026-07-21T07:17:08.004Z"
    }
  ]
}
```

The documented positions are:

`primary`, `up`, `up_right`, `right`, `down_right`, `down`, `down_left`,
`left`, `up_left`, and `composite`.

`composite` is a 3 by 3 summary grid rather than one of the nine gaze captures.

The live session inventory also contains `consent` in `capturedPositions`.
It is an auxiliary session artifact rather than a gaze position and was not
returned by `/listImages` for the sampled complete session.

### `GET /image`

Required query parameters:

- `sessionId`
- `filename`, copied exactly from `/listImages`

A successful response is raw `image/jpeg` bytes. The probe validates content
type, a 50 MB safety limit, JPEG signature, Pillow decoding, dimensions, and
SHA-256 entirely in memory. It does not save the image.

## Write endpoint reserved for a later phase

`POST /annotations` appends labels for a session and requires a write-enabled
key. The current probe and proposed EncounterSet intake need read access only.

The documented label convention is `aiims-eom-v1`. Bounding boxes use absolute
image pixels with top-left origin and fields `x`, `y`, `w`, `h`, and `cls`.
Suggested classes include `eye_region`, `iris`, `pupil`, `limbus`, `sclera`,
`upper_lid`, `lower_lid`, and `lesion`.

The supplied documents contain an ambiguity that must be resolved before label
submission is implemented: they allow splitting more than 200 annotations over
multiple requests but also state that the newest submission replaces the
session and partial submissions are not merged.

## Errors and limits

Non-successful responses are documented as JSON:

```json
{"error": "machine-code", "message": "human-readable message"}
```

| HTTP status | Meaning |
|---|---|
| 400 | Missing or invalid parameter |
| 401 | Missing, invalid, or revoked API key |
| 403 | Site not permitted, resource unavailable, or read-only key used for annotations |
| 404 | Session or image not found |
| 413 | Annotation request exceeds 512 KB |

The probe reports only the status and a restricted enum-like error code. It
does not echo upstream bodies because they may contain sensitive values.

## Candidate EncounterSet metadata mapping

The importer persists these values in the canonical EncounterSet metadata model.

| Upstream field | Existing IITK EncounterSet metadata field |
|---|---|
| `mrn` | `patient.hospital_UHID` and core patient identifier |
| `age` | `patient.patient_age_yrs` |
| `gender` | `patient.sex` |
| `site` | `patient.site_recruitment` |
| `sessionId` | `encounter.session_id` and source identity |
| `startedAt` | `encounter.capture_datetime` and core capture date |
| `diagnosis` / `diagnosisOther` | `encounter.patient_diagnosis` |
| `mode` | `encounter.mode_capture` |
| `eye` | `encounter.eye_laterality` |
| `capturedPositions` | `encounter.gaze` |
| image `position` | spatial position and `strabismus_gaze_position` |

`startedAt` is normalized to an explicit UTC ISO timestamp before it is saved
as `encounter.capture_datetime`, and the core capture date is derived from that
UTC value. A timezone-less upstream timestamp is treated as UTC. The exact
upstream string remains available in the IITK source-link audit metadata.

Remote diagnosis is metadata only. It must not choose grading schemes or task
routing; those remain owned by the configured Upload & Grading Profile.

## Probe usage

```bash
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py list-sessions --limit 3
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py list-images --session-id SESSION_ID
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py image-info --session-id SESSION_ID --filename FILENAME
UV_CACHE_DIR=/tmp/.uv-cache uv run python scripts/probe_iitk_api.py sample --limit 3
```

The `sample` command performs three read-only calls:

1. Fetch up to three sessions.
2. Select the first complete session and fetch its image inventory.
3. Fetch the first JPEG into memory and report sanitized validation metadata.

It prints JSON to stdout only. MRNs, free text, clinician identifiers, exact
session IDs, and filenames are removed or replaced with one-way short
references.

## Sanitized live observations

The read-only probe was run on 2026-08-01 against three recent sessions. The
following structural observations contain no patient values or source
identifiers:

- Pagination was active: a non-empty `nextPageToken` followed the three rows.
- Both `partial` and `complete` statuses were present.
- The documented session keys and image keys matched the live response; no
  additional object keys were observed.
- `capturedPositions` included the undocumented auxiliary value `consent`.
- One complete session reported 11 captured items: nine gaze positions,
  `composite`, and `consent`. Its `/listImages` response contained 10 JPEG
  entries, covering the nine gaze positions plus `composite`; `consent` was
  absent.
- The image inventory declared `image/jpeg` with `.jpg` filenames.
- One image fetched into memory decoded successfully as a 1040 by 640 JPEG and
  was 302,855 bytes. It was not written to disk.

No raw response, patient metadata, filename, session identifier, token, image
hash, or image file is stored in the repository.

## Local integration API

The application now stores one encrypted IITK configuration per project and
imports upstream sessions as project-scoped EncounterSets. Configuration and
sync endpoints require an authenticated `admin`, `local_admin`, or
`data_manager`; unsafe methods require the normal CSRF token.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/iitk/projects/<project_id>/configuration` | Read the project IITK flag, token status, and derived intake target |
| `POST/PATCH` | `/api/iitk/projects/<project_id>/configuration` | Enable/disable IITK intake and save or rotate its encrypted token |
| `GET` | `/api/iitk/configurations` | List configurations visible through the manager's lab-unit scope |
| `GET` | `/api/iitk/site-mappings` | List IITK site-to-hospital/lab-unit mappings and local resolution status |
| `POST` | `/api/iitk/configurations` | Save a project configuration and encrypted API token |
| `POST/PATCH` | `/api/iitk/configurations/<id>` | Update settings or rotate the token; a blank token preserves the current secret |
| `GET` | `/api/iitk/configurations/<id>/sessions` | Browse a live upstream session page using documented filters |
| `POST` | `/api/iitk/configurations/<id>/sync` | Queue an incremental sync; pass `full=true` for a full configured-date scan |

The supported administration surface is the selected project workspace under
`GET /admin/upload-projects`. It exposes only `active` (labelled **IITK API
populated project**) and `api_token`. A token is required the first time the
project is enabled; a blank token on later updates preserves the current
secret. Disabling the flag retains the encrypted token and synchronization
history so the connection can be re-enabled. IITK target-readiness warnings
are evaluated only for enabled IITK projects; ordinary projects do not show
IITK configuration warnings.

The service derives `project_upload_profile_id`, `encounter_set_type_id`, the
default intake lab/hospital, and an unambiguous optional camera from the
project's existing active Upload Profile and EncounterSetType configuration.
When an active `IITK-zips` EncounterSetType is present it is preferred as the
existing IITK metadata target; otherwise the project must have exactly one
active EncounterSetType target. The legacy IITK ZIP-import enable flag is not
used as the API-populated-project flag.

Example mutation (unsafe methods require the normal CSRF token):

```http
POST /api/iitk/projects/42/configuration
Content-Type: application/json
X-CSRFToken: <csrf-token>

{"active": true, "api_token": "<secret>"}
```

The older configuration mutation endpoints accept explicit target IDs for
backward compatibility, but the admin UI no longer exposes that duplicate
configuration form.

The token is encrypted with a per-record salt and is never returned by the
API. Configuration responses expose only `token_configured: true|false`.

### Site destination mapping

The IITK module owns a versioned `site_mappings.json` file. It resolves target
records by the exact hospital and lab-unit names rather than environment-
specific numeric IDs:

| IITK site | Local hospital | Local lab unit |
|---|---|---|
| `delhi` | RPC AIIMS | Deepsekhar Das |
| `kalyani` | AIIMS Kalyani | Ophthalmology |
| `bilaspur` | AIIMS Bilaspur | Ophthalmology |
| `nagpur` | AIIMS Nagpur | Ophthalmology |

Example `GET /api/iitk/site-mappings` response:

```json
{
  "success": true,
  "data": [
    {
      "site": "delhi",
      "hospital": "RPC AIIMS",
      "lab_unit": "Deepsekhar Das",
      "hospital_id": 1,
      "lab_unit_id": 6,
      "resolved": true
    }
  ]
}
```

This read endpoint requires an authenticated `admin`, `local_admin`, or
`data_manager`. It has no request body and does not require CSRF because it is
read-only.

The upstream site is retained as immutable `upload.source_site`. On first
import it also initializes the editable `patient.site_recruitment` field. A
known editable value assigns the EncounterSet lab unit and every image's
hospital during import. Verification edits apply the same remapping
immediately. Subsequent IITK synchronization does not overwrite the edited
patient field.

An unknown site or a named target missing from the local database does not
block ingestion. The EncounterSet remains in the configuration's default
intake lab and receives `upload.site_mapping_status` of `unmapped` or
`target_missing` for correction during verification.

## Synchronization behavior

- Every upstream session is imported, including `partial` sessions with zero
  images.
- `(configuration, sessionId)` is the idempotent source identity. A partial
  session that gains images or becomes complete updates the existing
  EncounterSet.
- Patient, encounter, and upload metadata are stored in the canonical nested
  EncounterSet `metadata_json` scopes. Existing locally managed keys in those
  scopes are preserved when source-owned keys are refreshed.
- Images use random local filenames. The exact IITK inventory filename is
  retained as `source_filename` in image metadata, alongside its SHA-256
  fingerprint, because annotation submissions must reference the exact
  filename returned by `GET /listImages`. An inventory-only sync backfills the
  field on previously imported images without downloading unchanged bytes.
- JPEGs are size-checked, decoded, stripped of EXIF, stored locally, and
  thumbnailed. Unchanged inventory entries are not downloaded again; a missing
  local file is recovered on the next sync.
- Images absent from a later inventory remain stored for history and receive
  `source_present: false`.
- All imported images have `creates_task=false`. Synchronization does not run
  verification or create grading tasks.
- A failed image does not prevent the session metadata or other images from
  being saved. Each individual network request or HTTP `429`/`5xx` response is
  retried once after 5 seconds. Configuration, contract, authentication,
  authorization, invalid-parameter, and not-found failures are not retried;
  they remain visible for correction and the next scheduled/manual sync.
- Requests are sequentially paced at no more than approximately 60 per minute,
  matching the supplied provider guidance. Incremental runs use a one-day
  overlap and do not repeat a second unbounded scan of every historical partial
  session. A manual `full=true` sync remains available when older sessions need
  reconciliation.

The database-backed Celery Beat schedule runs at minute `30`, UTC hours
`1-12`, which is exactly hourly from 07:00 through 18:00 IST. It dispatches
one maintenance-queue task for every active project configuration. A running
sync refreshes its database heartbeat during pagination, inventory work, and
each committed session. A separate maintenance-only check runs every five
minutes and requeues only locks whose heartbeat has stopped for 15 minutes.
This recovers worker/container interruptions without overlapping an active sync
or adding requests during healthy operation. Outside 07:00 through 18:00 IST,
the check clears a stale lock but defers its API work to the next scheduled
business-hours dispatch.

The retired `GET /admin/iitk` URL redirects to `GET /admin/upload-projects`.
Imported records appear in the existing EncounterSet browser with an `IITK
partial` or `IITK complete` badge.
