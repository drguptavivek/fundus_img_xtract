# Glaucoma AI Upload API

Uploads 1-10 direct fundus images through a selected Upload Profile, creates unverified direct-image records plus glaucoma tasks for AI processing, queues the linked Wadhwani glaucoma AI model, and returns upload/task identifiers immediately. Human grading still requires the normal verification workflow for newly stored images.

The browser page, this JWT API, and `/api/mobile/v1/uploads` all use the same direct-upload job service for direct-image persistence. They create `DirectImageUpload`, `Job`, `JobItem`, and `GradingTask` records through the shared service; endpoint differences are limited to authentication, response shape, and Wadhwani-specific enqueue/result presentation.

Duplicate direct images are detected globally by content hash. A duplicate
attempt does not create a new `DirectImageUpload`, direct-image verification
row, verification job, thumbnail job, metadata job, PII job, or uploader
file-count increment. The current upload job keeps a visible duplicate item
pointing to the canonical older image. Because the caller submitted identical
bytes, the API may return that canonical image's thumbnail, task, and AI result.
AI reuse is limited to the Wadhwani model linked to the selected upload profile;
human grades are never copied or created by duplicate handling.

## `POST /api/glaucoma-ai/uploads`

- Auth: Bearer JWT from `/api/mobile/v1/auth/login`.
- Roles: `admin`, `local_admin`, `data_manager`, `ophthalmologist`, `optometrist`, or `fileUploader`.
- CSRF: not required because the route uses bearer-token auth.
- Scope: the token user must submit a concrete active upload profile for the selected project, lab unit, glaucoma disease, camera, site, and mydriatic state. That profile must enable a direct-image AI workflow linked to the enabled Wadhwani glaucoma model.
- Body: `multipart/form-data`.

### Form Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `project_id` | integer | yes | Active project in the caller's upload profile. |
| `lab_unit_id` | integer | yes | Explicitly assigned lab unit. |
| `profile_id` | integer | yes | Concrete assigned upload profile selected from `/api/mobile/v1/upload-options`. |
| `camera_id` | integer | yes | Camera allowed by the upload profile. |
| `area_id` | integer | yes | Site/area allowed by the upload profile. |
| `is_mydriatic` | boolean-ish | no | Accepts `1`, `true`, `yes`, or `on`. Defaults false. |
| `files` | file[] | yes | 1-10 JPG/PNG images. |

## `GET /api/glaucoma-ai/uploads/<image_uuid>/image`

- Auth: same bearer JWT and role set as upload creation.
- Scope: the image must have been uploaded by the token user.
- Response: image bytes for the final image variant, preferring edited image when present.

## `GET /api/glaucoma-ai/uploads/<image_uuid>/thumbnail`

- Auth: same bearer JWT and role set as upload creation.
- Scope: the image must have been uploaded by the token user.
- Response: thumbnail image bytes. Existing thumbnails are served when present; otherwise the endpoint generates a thumbnail on demand from the final image variant.

## `GET /api/glaucoma-ai/uploads/recent`

Returns recent glaucoma AI uploads for the logged-in token user only.

- Auth: same bearer JWT and role set as upload creation.
- Scope: `DirectImageUpload.uploader_id` must equal the token user ID, disease must be glaucoma, and the image must have been created by the Wadhwani glaucoma AI upload flow or linked from that user's mobile direct-upload job. Admin/local-admin/data-manager roles do not expand this list.
- Query parameters:
  - `limit`: optional, default `20`, maximum `100`.
  - `offset`: optional, default `0`.

Response:

```json
{
  "items": [
    {
      "upload_id": 123,
      "image_uuid": "9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d",
      "filename": "disc.jpg",
      "created_at": "2026-04-30T10:15:00+00:00",
      "project": { "id": 1, "name": "Screening Project" },
      "hospital": { "id": 1, "name": "Hospital" },
      "lab_unit": { "id": 2, "name": "Retina Unit" },
      "camera": { "id": 1, "name": "Camera" },
      "area": { "id": 1, "name": "Site" },
      "disease": { "id": 2, "name": "Glaucoma" },
      "task_id": 456,
      "task_uuid": "0a1d3c2f-5e61-40d0-94c0-b34040dc73ab",
      "task_state": "pending",
      "image_url": "http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/image",
      "thumbnail_url": "http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/thumbnail",
      "result_url": "http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/result",
      "inference": {
        "status": "success",
        "confidence": 0.91,
        "predicted_class": 1,
        "predicted_class_name": "glaucoma",
        "grade_impression": "Glaucoma"
      }
    }
  ],
  "limit": 20,
  "offset": 0,
  "count": 1
}
```

## `GET /api/glaucoma-ai/uploads/recent/results`

Returns a compact result-only payload for polling. Use this endpoint when a mobile or JavaScript client already has the image list and only needs fresh inference status.

- Auth: same bearer JWT and role set as upload creation.
- Scope: same as `/recent`; only the token user's Wadhwani glaucoma AI uploads are returned.
- Query parameters:
  - `limit`: optional, default `20`, maximum `100`.
  - `offset`: optional, default `0`.
- Media: no `image_url` or `thumbnail_url` fields are returned, so clients should not reload images while polling this endpoint.

Response:

```json
{
  "items": [
    {
      "upload_id": 123,
      "image_uuid": "9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d",
      "filename": "disc.jpg",
      "task_id": 456,
      "task_uuid": "0a1d3c2f-5e61-40d0-94c0-b34040dc73ab",
      "task_state": "pending",
      "inference": {
        "status": "success",
        "ai_model_id": 1,
        "ai_model_name": "wai_glaucoma_ver1",
        "ai_model_version": "20Oct2025",
        "inference_run_id": 121,
        "grade_id": 26425,
        "prediction_id": "8356fa13-7c7a-43d8-95d1-10a0b03bd92b",
        "confidence": 0.7462,
        "predicted_class": 1,
        "predicted_class_name": "Glaucoma Present",
        "prediction": "referrable",
        "grade_impression": "Glaucoma",
        "error_code": null,
        "started_at": "2026-04-30T12:21:27.252216+00:00",
        "finished_at": "2026-04-30T12:21:28.898338+00:00"
      }
    }
  ],
  "limit": 20,
  "offset": 0,
  "count": 1
}
```

## `GET /api/glaucoma-ai/uploads/<image_uuid>/result`

Returns one glaucoma AI upload/result record for the logged-in token user only.

- Auth: same bearer JWT and role set as upload creation.
- Scope: `DirectImageUpload.uploader_id` must equal the token user ID and the image must have been created by the Wadhwani glaucoma AI upload flow or linked from that user's mobile direct-upload job.
- Response: one item with the same shape used by `items[]` in `/recent`.

### Success Response

Status: `201 Created`

```json
{
  "success": true,
  "success_count": 1,
  "error_count": 0,
  "items": [
    {
      "filename": "disc.jpg",
      "status": "queued",
      "message": "Image uploaded and Wadhwani glaucoma inference queued.",
      "upload_id": 123,
      "image_uuid": "9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d",
      "task_id": 456,
      "task_uuid": "0a1d3c2f-5e61-40d0-94c0-b34040dc73ab",
      "job_token": "5c9467c4e7a04e5ebfc03f0f3e22dc3d",
      "image_url": "http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/image",
      "inference": null
    }
  ]
}
```

### Validation and Error Responses

- `400`: missing form fields, invalid upload scope, no files, more than 10 files, unsupported MIME type, oversized image, or no successful items.
- `401`: missing, expired, or invalid JWT.
- `403`: inactive user or token roles do not permit upload/inference.
- Per-file failures are returned in `items` with `status: "error"` or `status: "enqueue_failed"`.
- Duplicate direct images are represented as links to the existing canonical `DirectImageUpload`. The upload job item stores the existing image UUID and task ID, so the caller can display the previous thumbnail and the latest, pending, or newly queued Wadhwani result for the selected profile's model.
- Successful uploads are stored as unverified direct images with a glaucoma task for AI inference. Human grading remains blocked until the image is verified through the normal verification workflow.
- Wadhwani inference runs asynchronously through `celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task`. Poll `/recent/results` or `/<image_uuid>/result` for `inference.status`; use `/recent/results` when avoiding media reloads.
- The Wadhwani client reuses process-local HTTPS connections and retries idempotent presigned S3 `PUT` uploads up to three times for transient connection, DNS, throttling, or server failures. Upload errors stored in inference runs omit the presigned URL and signature.
- Each Wadhwani batch processes at most three images concurrently inside the existing general-worker container. HTTP sessions are thread-local, and unrelated queues retain the worker's existing execution model.

### Example

```bash
curl -X POST http://localhost:5001/api/glaucoma-ai/uploads \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F project_id=1 \
  -F lab_unit_id=2 \
  -F profile_id=12 \
  -F camera_id=1 \
  -F area_id=1 \
  -F is_mydriatic=false \
  -F files=@disc-1.jpg \
  -F files=@disc-2.jpg
```

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:5001/api/glaucoma-ai/uploads/recent?limit=20"
```

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  "http://localhost:5001/api/glaucoma-ai/uploads/recent/results?limit=20"
```

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/result
```

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/image \
  --output inference-image.jpg
```

```bash
curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:5001/api/glaucoma-ai/uploads/9f6efc5e-9a4e-4c20-9bc6-1d8d93449b8d/thumbnail \
  --output inference-thumbnail.jpg
```

## Browser Page

Session-authenticated users with the same role set can use `/glaucoma-ai/`. The page includes CSRF protection, renders uploaded images once, and polls `/glaucoma-ai/recent/results` for compact JSON updates so thumbnails are not repeatedly fetched.
