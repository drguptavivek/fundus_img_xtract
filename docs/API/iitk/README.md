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

This is a discovery mapping, not implemented persistence behavior yet.

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
