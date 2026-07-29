# Mobile EIM Uploads

Base path: `/api/mobile/v1`

This contract covers mobile EIM upload and inferencing entrypoints. EIM means the upload package that creates or queues Eye Image Management records and, when configured, links them to downstream AI inference work.

## Vocabulary

- `upload_profile`: server-side upload policy selected from `GET /upload-options`.
- `upload_kind`: the concrete ingestion path for one upload request.
- `upload_token`: opaque token returned after upload creation and used for status and inference polling.
- `idempotency_key`: client-generated opaque key for one upload attempt; used to make retries and network-drop recovery safe.
- `job`: server-side upload tracker containing one or more uploaded items.
- `item`: a file or image row attached to the job.

Mobile supports only these `upload_kind` values:
- `direct_image`
- `remidio`
- `encounter_set`

`pregraded` is webapp-only. Mobile clients must not display or submit it.

## Profile Selection

Clients must call `GET /upload-options`, let the user or app choose one concrete `profile_id`, and submit that `profile_id` to `POST /uploads`.

A profile may allow multiple `upload_kinds`, but each upload request chooses exactly one `upload_kind`. The selected profile is the source of truth for project, lab unit, disease, camera, area, mydriatic policy, and AI workflow availability. The backend revalidates all submitted IDs against the selected profile.

## Auth And Scope

- Auth: `Authorization: Bearer <access_token>`
- Role: `fileUploader`
- CSRF: not required; this is a bearer-token mobile JSON/multipart surface.
- Scope: uploads are limited to the authenticated user's active mobile session, lab-unit assignments, disease/profile permissions, and the selected upload profile.
- Status and inference reads are scoped to the original uploader. A user cannot read another user's `upload_token`.

## `POST /uploads`

Content type: `multipart/form-data`

Common fields:
- `idempotency_key`: required string, unique per upload attempt for the authenticated user
- `profile_id`: required positive integer
- `upload_kind`: required, one of `direct_image`, `remidio`, `encounter_set`
- `project_id`: required positive integer
- `lab_unit_id`: required positive integer

Success response: `201 Created`. Replaying the same `idempotency_key` returns `200 OK` with the existing upload job instead of creating another job.

```json
{
  "upload_token": "uuid",
  "upload_kind": "direct_image",
  "profile_id": 100,
  "status": "completed",
  "uploaded_count": 1,
  "duplicate_count": 0,
  "accepted_count": 1,
  "rejected_count": 0,
  "inference_available": false
}
```

`encounter_set` responses also include `encounter_uuid`.

### Direct Image

Use for independent fundus image files.

Direct-image duplicate detection is global by image content hash. A duplicate
attempt does not create another `DirectImageUpload`, direct-image verification
row, verification job, thumbnail job, metadata job, PII job, or uploader
file-count increment. The upload job still returns a visible item with
`state: "duplicate"` pointing to the canonical older image UUID/task. Its
thumbnail and current-profile Wadhwani AI result may be returned because the
caller submitted the same image bytes. If the canonical image lacks a usable AI
grade for the Wadhwani model linked to the selected upload profile, the server
may create/reuse the canonical disease task and queue or retry AI inference for
that canonical image. Human grades are never copied by duplicate handling.

Direct-image counts distinguish new images from duplicate links:
- `uploaded_count`: newly created `DirectImageUpload` rows.
- `duplicate_count`: duplicate attempts linked to canonical images.
- `accepted_count`: uploaded plus duplicate items.
- `rejected_count`: invalid or failed items.

Required fields:
- common fields above
- `disease_id`
- `camera_id`
- `area_id`
- `files`: one or more image files

Optional fields:
- `is_mydriatic`: boolean-like value; profile default is used when omitted
- `remarks`: plain text, see Remarks Policy

Example:

```bash
curl -X POST http://localhost:5001/api/mobile/v1/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -F "profile_id=100" \
  -F "idempotency_key=$UPLOAD_ATTEMPT_KEY" \
  -F "upload_kind=direct_image" \
  -F "project_id=10" \
  -F "lab_unit_id=12" \
  -F "disease_id=2" \
  -F "camera_id=3" \
  -F "area_id=4" \
  -F "is_mydriatic=false" \
  -F "remarks=patient reported blurred vision" \
  -F "files=@right-eye.png"
```

### Remidio

Use for Remidio ZIP packages queued for later processing.

Required fields:
- common fields above
- `camera_id`
- `files`: one or more `.zip` files

ZIP files may contain only `.jpg`, `.jpeg`, and `.pdf` entries. Empty ZIPs, unsafe paths, and unsupported file types are rejected.

Example:

```bash
curl -X POST http://localhost:5001/api/mobile/v1/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -F "profile_id=100" \
  -F "idempotency_key=$UPLOAD_ATTEMPT_KEY" \
  -F "upload_kind=remidio" \
  -F "project_id=10" \
  -F "lab_unit_id=12" \
  -F "camera_id=3" \
  -F "files=@remidio.zip"
```

### Encounter Set

Use when one patient encounter contains multiple positioned images.

Required fields:
- common fields above
- `encounter_json`: JSON object
- one multipart file part for each `items[].file_key`

`encounter_json` fields:
- `patient_id`: required string
- `patient_name`: required string
- `capture_date`: required `YYYY-MM-DD` string
- `disease_id` or `disease_ids`: required
- `remarks`: optional encounter-level plain text
- `referral_suggestion`: optional encounter-level tri-state value, one of `yes`, `no`, `missing`
- `items`: required non-empty array

Each `items[]` entry:
- `file_key`: multipart field name containing this image file
- `spatial_position`: unique integer from 1 to 9
- `camera_id`: positive integer allowed by the profile
- `area_id`: positive integer allowed by the profile
- `is_mydriatic`: optional boolean-like value
- `remarks`: optional image-level plain text
- `referral_needed_or_positive_image`: optional image-level tri-state value, one of `yes`, `no`, `missing`
- `refrralneed_or_positive_image`: accepted alias for `referral_needed_or_positive_image`

The `file_key` value is a mapping key, not a filename. For example, `file_key: "right_eye"` requires a multipart part named `right_eye`.

Example:

```bash
curl -X POST http://localhost:5001/api/mobile/v1/uploads \
  -H "Authorization: Bearer $TOKEN" \
  -F "profile_id=100" \
  -F "idempotency_key=$UPLOAD_ATTEMPT_KEY" \
  -F "upload_kind=encounter_set" \
  -F "project_id=10" \
  -F "lab_unit_id=12" \
  -F 'encounter_json={
    "patient_id":"MRN-123",
    "patient_name":"Mobile Patient",
    "capture_date":"2026-05-03",
    "disease_ids":[2],
    "referral_suggestion":"missing",
    "items":[
      {"file_key":"right_eye","spatial_position":1,"camera_id":3,"area_id":4,"referral_needed_or_positive_image":"yes"},
      {"file_key":"left_eye","spatial_position":2,"camera_id":3,"area_id":4,"referral_needed_or_positive_image":"no"}
    ]
  }' \
  -F "right_eye=@right-eye.png" \
  -F "left_eye=@left-eye.png"
```

Encounter-set image files must be `.jpg`, `.jpeg`, or `.png`.

## `GET /uploads/<upload_token>`

Returns upload status for the authenticated uploader.

Success response: `200 OK`

```json
{
  "upload_token": "uuid",
  "upload_kind": "direct_image",
  "profile_id": 100,
  "status": "completed",
  "error": null,
  "rejected_summary": null,
  "created_at": "2026-05-03T12:00:00Z",
  "updated_at": "2026-05-03T12:00:00Z",
  "items": [
    {
      "id": 1,
      "filename": "right-eye.png",
      "state": "completed",
      "detail": "Image uploaded successfully.",
      "source_type": "direct_image",
      "source_id": 55,
      "source_uuid": "uuid",
      "thumbnail_url": "/api/mobile/v1/uploads/uuid/images/image-uuid/thumbnail",
      "task_id": 99,
      "started_at": null,
      "finished_at": "2026-05-03T12:00:00Z"
    }
  ]
}
```

## `GET /uploads/by-idempotency-key/<idempotency_key>`

Returns upload status for an upload attempt when the client lost the POST response or otherwise does not know the `upload_token`.

Success response: `200 OK`; response shape is the same as `GET /uploads/<upload_token>`.

Clients should persist `idempotency_key` before starting the multipart request. If the POST fails with an ambiguous network error, call this endpoint before offering a retry. If it returns `404`, the server did not commit that upload attempt.

## `GET /uploads/<upload_token>/inference`

Returns inference state for task-linked upload items.

Success response: `200 OK`

```json
{
  "upload_token": "uuid",
  "status": "running",
  "items": [
    {
      "filename": "disc.jpg",
      "state": "ok",
      "source_uuid": "image-uuid",
      "thumbnail_url": "/api/mobile/v1/uploads/uuid/images/image-uuid/thumbnail",
      "task_id": 123,
      "inference": {
        "task_id": 123,
        "provider": "wadhwani_glaucoma",
        "status": "success",
        "prediction_id": "remote-prediction-id",
        "execute_response": {
          "results": [
            {
              "prediction": "referrable",
              "predicted_class": 1,
              "predicted_class_name": "Glaucoma Present",
              "model_score": 0.523
            }
          ]
        },
        "error_code": null,
        "error_message": null,
        "updated_at": "2026-05-05T05:30:00+00:00"
      }
    }
  ],
  "results": [
    {
      "task_id": 123,
      "provider": "wadhwani_glaucoma",
      "status": "success",
      "prediction_id": "remote-prediction-id",
      "execute_response": {
        "results": [
          {
            "prediction": "referrable",
            "predicted_class": 1,
            "predicted_class_name": "Glaucoma Present",
            "model_score": 0.523
          }
        ]
      }
    }
  ]
}
```

`status` values:
- `not_configured`: no task-linked items exist
- `pending`: at least one task-linked item has no recorded inference run yet
- `running`: at least one inference run is still in progress
- `complete`: all task-linked items succeeded
- `partial`: at least one task-linked item succeeded and at least one failed
- `failed`: at least one task-linked item failed and none are still pending/running

The `items` array is the UI source of truth for polling. Each image returns its own `inference` object as soon as that image has a known result, so clients should update image tiles independently and should not wait for the whole upload batch to complete.

Result fields, when present:
- `task_id`
- `ai_model_id`
- `provider`
- `status`
- `prediction_id`
- `execute_response`
- `error_code`
- `error_message`
- `updated_at`

Clients should display Wadhwani result text from the remote payload without deriving present/absent from local grade labels. For glaucoma, use `execute_response.results[0].predicted_class_name` and show `model_score` or `confidence` as a percent with one decimal place.

## `POST /uploads/<upload_token>/inference/retry`

Queues Wadhwani inference again for failed image tasks in a mobile upload. Passing `task_ids` limits the retry to specific images; omitting it retries all failed task-linked images in the upload.

Request:

```json
{
  "task_ids": [123]
}
```

Success response: `202 Accepted`

```json
{
  "upload_token": "uuid",
  "retry_job_token": "retry-job-uuid",
  "queued_task_ids": [123],
  "queued_count": 1
}
```

Errors:
- `400 inference_not_configured`: the upload has no task-linked images or the requested task IDs do not belong to this upload
- `409 no_failed_inference`: no selected image currently has a failed inference run

## `GET /uploads/<upload_token>/images/<image_uuid>/thumbnail`

Returns the uploaded direct-image thumbnail for the authenticated uploader. This route uses the same mobile bearer token as other mobile API calls, so native clients should send `Authorization: Bearer <token>` when rendering cached recent results.

Success response: `200 OK` with an image content type.

The `image_uuid` must belong to the requested `upload_token`; otherwise the API returns `404`.

Mobile clients should keep compact recent-result metadata for 7 days and use the `thumbnail_url` from upload status for image display. Do not rely on local picker file paths because they are not stable across Flutter Web, Android, iOS, and Windows app restarts.

Direct-image duplicates are not dead rejected rows. When the shared direct-upload service detects a duplicate, the `JobItem` for the current upload attempt is stored with `state: "duplicate"` and points to the existing canonical `DirectImageUpload` through `source_id` and `source_uuid`. The mobile status payload returns that existing image UUID, thumbnail URL, and task ID so the app can show the duplicate thumbnail and refresh the latest Wadhwani result for the existing task. If no task exists yet for the duplicate image and selected disease, the service creates one before enqueueing inference.

## Flutter PWA Serving

The Flutter web/PWA app shell can be served by Flask at `/mobile/`; a separate nginx router is not required for this route. Build the PWA with:

```bash
make mobile-pwa-build
```

The target builds `apps/fundus_glaucoma_mobile` with `--base-href /mobile/` and copies the generated files into `static/mobile-pwa/`. If `apps/fundus_glaucoma_mobile/.env` exists, the target reads it before building; `FUNDUS_API_BASE_URL=https://eyeimg.aiims.edu.in` pins the generated PWA bundle to that API origin. When no `FUNDUS_API_BASE_URL` build define is present, Flutter Web uses the current serving origin as its default server URL. Android APK/AAB binaries are published as assets on the `fundus_glaucoma_mobile` GitHub Releases page; `/mobile/download/android` and `/mobile/download/android-bundle` redirect there instead of serving large binaries from Flask. Flask serves `index.html` for `/mobile/` and deep links under `/mobile/*`, while `/api/mobile/v1/*` remains the authenticated JSON API used by Android, iOS, Windows, and PWA clients.

## Remarks Policy

`remarks` fields are plain text only. Clients should send human-entered notes as text, not HTML or structured JSON. The backend trims surrounding whitespace, stores blank remarks as `null`, allows newlines and tabs, rejects unsupported control characters, and limits remarks to 1000 characters.

## Client Validation

Clients should validate before upload:
- bearer token is present and current
- a new `idempotency_key` has been generated and persisted before POST
- selected profile exists in the latest `/upload-options` response
- selected `upload_kind` is present in `profile.upload_kinds`
- one upload request contains exactly one `upload_kind`
- all submitted project, lab, disease, camera, area, and mydriatic values are allowed by the selected profile
- required files are present and use supported extensions
- POST retries reuse the same `idempotency_key`; never generate a new key for an ambiguous retry
- encounter-set `file_key` values match multipart part names
- encounter-set positions are unique integers from 1 to 9
- remarks are plain text and no longer than 1000 characters

Client validation is for user experience only. Backend validation is authoritative.

## Errors

Errors use JSON:

```json
{
  "error": "profile_scope_mismatch",
  "message": "Selected profile does not match project or lab unit."
}
```

Common statuses:
- `400`: missing fields, invalid integers, unsupported upload kind, invalid files, invalid `encounter_json`, remarks too long
- `401`: missing, invalid, expired, or unmappable bearer token
- `403`: inactive user, missing `fileUploader` role, profile or scope mismatch
- `404`: `upload_token` not found in the authenticated uploader's scope

Common error codes:
- `idempotency_key_required`
- `upload_kind_required`
- `unsupported_upload_kind`
- `files_required`
- `profile_scope_mismatch`
- `disease_required`
- `disease_not_allowed`
- `encounter_json_required`
- `invalid_encounter_json`
- `items_required`
- `file_part_missing`
- `invalid_spatial_position`
- `invalid_filename`
- `invalid_file_type`
- `remarks_too_long`
- `invalid_remarks`
- `forbidden`
- `inactive_user`
- `upload_not_found`
