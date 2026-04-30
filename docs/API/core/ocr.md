# OCR / PII API

These routes manage PII OCR checks for visible images, including manual overrides.

Auth and CSRF:

- All routes require a logged-in session plus the roles listed below, except that the manual override still uses the session and therefore needs CSRF.
- `GET` routes do not require CSRF.
- `POST /api/ocr/pii/override` requires CSRF because it mutates session-authenticated state.

## Routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/ocr/pii/batch` | `POST` | Session + login + `admin`, `local_admin`, `data_manager`, `data_exporter`, `dataset_creator`, `analytics_viewer`, `fileUploader`, `optometrist`, `ophthalmologist`, `resident` | JSON `{ "image_uuids": [str, ...] }` | `{ "success": true, "data": { "<uuid>": object } }` | `400` if `image_uuids` is not a list. |
| `/api/ocr/pii/boxes/<string:image_uuid>` | `GET` | Same role set as above | Path `image_uuid` | `{ "success": true, "data": object }` | `404` if the image cannot be resolved. |
| `/api/ocr/pii/<string:image_uuid>` | `GET` | Same role set as above | Query param `refresh=1` optional | `{ "success": true, "data": object, "cached": bool }` | `404` if the image cannot be resolved. |
| `/api/ocr/pii/override` | `POST` | Same role set as above + CSRF | JSON `{ "image_uuid": str, "pii_status": "clear" \| "detected" }` | `{ "success": true, "data": object }` | `400` for missing or invalid fields. `404` if the image cannot be resolved. |

## `POST /api/ocr/pii/batch`

Request body:

```json
{ "image_uuids": ["img-1", "img-2"] }
```

If the list is empty after filtering invalid entries, the route returns:

```json
{ "success": true, "data": {} }
```

Per-image response shapes in `data`:

- Found and checked:
  - `status`
  - `label`
  - `variant`
  - `checked_at`
  - `source`
- Pending:
  - `status: "pending"`
  - `label: "Pending"`
  - `variant`
- Missing:
  - `status: "error"`
  - `label: "Image not found"`
  - `variant: null`

Example:

```json
{
  "success": true,
  "data": {
    "img-1": {
      "status": "clear",
      "label": "No PII detected",
      "variant": "orig",
      "checked_at": "2026-04-30T12:00:00+00:00",
      "source": "auto"
    }
  }
}
```

## `GET /api/ocr/pii/boxes/<string:image_uuid>`

The `data` object includes:

- `status`
- `label`
- `valid_detections`
- `pattern_matches`
- `detections`
- `roi`
- `duration_ms`
- `source`

When OCR has never run and no verification row exists, the route returns a synthetic `pending` or `error` response rather than a transport error.

## `GET /api/ocr/pii/<string:image_uuid>`

`refresh=1` forces bypass of the in-process cache. If a manual override exists, the route returns that manual state immediately with `cached: false`.

Returned `data` keys:

- `status`
- `label`
- `valid_detections`
- `pattern_matches`
- `version`
- `duration_ms`
- `source`

## `POST /api/ocr/pii/override`

Request body:

```json
{ "image_uuid": "img-uuid", "pii_status": "clear" }
```

Successful response:

```json
{
  "success": true,
  "data": {
    "status": "clear",
    "label": "No PII detected",
    "source": "manual",
    "image_uuid": "img-uuid",
    "image_variant": "orig"
  }
}
```

Side effect from code:

- The dataset-screen cache is cleared after a successful manual override.
