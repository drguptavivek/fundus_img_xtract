# OCR / PII API

These routes manage PII OCR checks for visible images, including manual overrides.

Auth and CSRF:

- All routes require a logged-in session plus `media.ocr_pii.read` or `media.ocr_pii.process` authorization for every referenced image.
- Classical and project authority is resolved centrally, and no OCR record or cache is read before object authorization.
- `GET` routes do not require CSRF.
- `POST /api/ocr/pii/override` requires CSRF because it mutates session-authenticated state.

## Routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/ocr/pii/batch` | `POST` | Session + `media.ocr_pii.read` per UUID | JSON `{ "image_uuids": [str, ...] }` | `{ "success": true, "data": { "<uuid>": object } }` | `400` if `image_uuids` is not a list. |
| `/api/ocr/pii/boxes/<string:image_uuid>` | `GET` | Session + `media.ocr_pii.process` | Path `image_uuid` for an EncounterFile, DirectImageUpload, or locally stored EncounterSetImage | `{ "success": true, "data": object }` | Non-disclosing `404` if the image cannot be authorized and resolved. |
| `/api/ocr/pii/<string:image_uuid>` | `GET` | Session + `media.ocr_pii.process` | Query param `refresh=1` optional; supports EncounterFile, DirectImageUpload, and locally stored EncounterSetImage UUIDs | `{ "success": true, "data": object, "cached": bool }` | Non-disclosing `404` if the image cannot be authorized and resolved. |
| `/api/ocr/pii/override` | `POST` | Session + `media.ocr_pii.process` + CSRF | JSON `{ "image_uuid": str, "pii_status": "clear" \| "detected" }` | `{ "success": true, "data": object }` | `400` for missing or invalid fields. `404` if the image cannot be authorized and resolved. |

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
