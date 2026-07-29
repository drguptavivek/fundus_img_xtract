# Encounter Set API

These endpoints manage set-based encounter viewing, image reordering, and mobile uploads.

Auth and CSRF:

- `GET` routes require a logged-in session and the roles shown below.
- The browser-session `POST` route for image reordering requires CSRF protection.
- The mobile upload route uses `@token_auth_required` and is exempt from the session CSRF guard.

## Routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/v1/encounter-set/unverified` | `GET` | Session + login + `admin`, `local_admin`, `optometrist` | None | Array of `{ "uuid": str, "patient_id": str, "patient_name": str, "capture_date": date \| datetime, "image_count": int }` | `403` on role failure. `500` on unexpected server error. |
| `/api/v1/encounter-set/<uuid>/details` | `GET` | Session + login + `admin`, `local_admin`, `optometrist` | Path `uuid` | `{ "uuid": str, "patient_id": str, "patient_name": str, "capture_date": date \| datetime, "referral_suggestion": "yes" \| "no" \| "missing", "referral_positive_diseases": [str], "images": [{"uuid": str, "spatial_position": int, "referral_needed_or_positive_image": "yes" \| "no" \| "missing", "url": str, "thumbnail_url": str \| null}] }` | `404` if the encounter is not found or not in scope. `403` on role failure. `500` on unexpected server error. |
| `/api/v1/encounter-set/image/<uuid>/position` | `POST` | Session + login + `admin`, `local_admin`, `optometrist` + CSRF | JSON body `{ "spatial_position": int }` | `{ "message": "Position updated" }` | `400` for missing or invalid position, `404` if the image is missing, `403` if access is denied, `409` on a unique-position conflict, `500` on unexpected DB error. |
| `/api/v1/encounter-set/upload` | `POST` | Bearer JWT via `@token_auth_required` + rate limit (`60 per minute`) | Multipart form-data | `{ "message": str, "encounter_id": int, "encounter_uuid": str, "image_uuid": str, "spatial_position": int, "referral_suggestion": "yes" \| "no" \| "missing", "referral_positive_diseases": [str], "referral_needed_or_positive_image": "yes" \| "no" \| "missing" }` | `400`, `401`, `403`, `404`, `413`, or `500` depending on validation and storage failure. |

## `GET /api/v1/encounter-set/unverified`

Returns set-based encounters that are not yet verified and are visible to the caller’s scope.

```json
[
  {
    "uuid": "enc-uuid",
    "patient_id": "P123",
    "patient_name": "Jane Doe",
    "capture_date": "2026-04-30",
    "image_count": 3
  }
]
```

## `GET /api/v1/encounter-set/<uuid>/details`

`images[].url` and `images[].thumbnail_url` are generated with `url_for()` for the media routes, so the exact path is owned by the media blueprint.

```json
{
  "uuid": "enc-uuid",
  "patient_id": "P123",
  "patient_name": "Jane Doe",
  "capture_date": "2026-04-30",
  "referral_suggestion": "missing",
  "referral_positive_diseases": [],
  "images": [
    {
      "uuid": "img-uuid",
      "spatial_position": 1,
      "referral_needed_or_positive_image": "missing",
      "url": "<media image URL>",
      "thumbnail_url": "<media thumbnail URL>"
    }
  ]
}
```

## `POST /api/v1/encounter-set/image/<uuid>/position`

Request body:

```json
{ "spatial_position": 1 }
```

Validation in code:

- `spatial_position` is required.
- It must be an integer.
- It must be between `1` and `9`.

Additional error bodies:

- `{"error": "Missing spatial_position"}`
- `{"error": "Invalid spatial_position", "message": "Must be an integer between 1 and 9"}`
- `{"error": "Invalid spatial_position", "message": "Must be between 1 and 9"}`
- `{"error": "Position already occupied", "message": "Another user moved an image to this position. Please try a different position."}`

## `POST /api/v1/encounter-set/upload`

Multipart form-data fields used by the code:

- `file` required
- `project_id` required
- `spatial_position` required, integer `1-9`
- `encounter_uuid` optional
- `disease_id` optional
- `patient_id` required when `encounter_uuid` is omitted
- `patient_name` required when `encounter_uuid` is omitted
- `capture_date` optional, defaults to the current UTC date as `YYYY-MM-DD`
- `referral_suggestion` optional for new encounters: `yes`, `no`, or `missing`
- `referral_positive_diseases` optional encounter-level list of referred/positive diseases or referral reasons. Values may be configured disease names or free text; repeated fields and comma/semicolon-separated values are accepted
- `referral_positive_disease` is accepted as an alias for `referral_positive_diseases`
- `referral_needed_or_positive_image` optional for this image: `yes`, `no`, or `missing`
- `refrralneed_or_positive_image` is accepted as a backward-compatible alias for `referral_needed_or_positive_image`

The route validates image extension, MIME type, magic bytes, file size, and image dimensions before creating or updating the encounter.

Typical validation failures:

- `401` from the bearer-token decorator when the token is missing, invalid, expired, or the token type is wrong.
- `403` when the upload token has no `lab_unit_id`, the token is not associated with a user, the project/scope check fails, or the encounter is outside the token’s lab unit.
- `400` for invalid form values or invalid image files.
- `413` when the file exceeds the size limit.
- `404` when a referenced encounter does not exist.

Successful response:

```json
{
  "message": "Image uploaded successfully",
  "encounter_id": 7,
  "encounter_uuid": "enc-uuid",
  "image_uuid": "img-uuid",
  "spatial_position": 1,
  "referral_suggestion": "missing",
  "referral_positive_diseases": [],
  "referral_needed_or_positive_image": "missing"
}
```

Implementation notes from the code:

- New images are saved under a generated UUID filename ending in `.jpg`.
- The route always sets `is_set_based=True` for new encounters.
- Thumbnail generation is scheduled after the database commit, but a thumbnail scheduling failure does not fail the upload response.
