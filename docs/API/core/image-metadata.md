# Image Metadata API

These routes expose extracted file metadata for encounter images and direct uploads.

Auth and CSRF:

- `GET` requires a logged-in session and the `media.metadata.read` object policy.
- `POST` requires `media.metadata.process` for the same image and CSRF because it uses the browser session.
- Classical role/scope, scoped project roles, legacy project capabilities, collaborator membership, and exact grading eligibility are resolved by the central authorization service. Metadata caches are read only after authorization.

## Routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/image-metadata/<string:image_uuid>` | `GET` | Session + `media.metadata.read` | Query params `variant`, `include_raw` | `{ "success": true, "data": object, "cached": bool }` | `404` if the image is missing, unauthorized, ambiguous, or metadata cannot be resolved. `500` on unexpected error. |
| `/api/image-metadata/<string:image_uuid>` | `POST` | Same as `GET` + CSRF | JSON body `{"variant", "include_raw", "force"}` | `{ "success": true, "data": object, "cached": false, "updated": bool }` | `404` if the image cannot be resolved. `500` if extraction fails. |

## Request details

### `variant`

- Encounter images always resolve to `orig`.
- Direct uploads accept `orig` and `edited`.
- If `variant` is omitted or invalid for a direct upload, the code uses `edited` when available, otherwise `orig`.
- If `variant=edited` is requested for a direct image without an edited file, the route returns `404`.

### `include_raw`

Truthy values accepted by the code:

- `GET`: `1`, `true`, `yes`
- `POST`: `true`, `1`, `yes`, and the boolean `true`

When `include_raw` is enabled, the response adds:

- `histogram_json`
- `exif_json`
- `iptc_json`

### `force` on `POST`

- `false` or omitted: return the stored metadata row if it already exists.
- `true`: recompute metadata from the file and upsert the row.

## Serialized `data` shape

The helper `_serialize_metadata()` returns:

- `image_uuid`
- `image_variant`
- `width`
- `height`
- `format`
- `mode`
- `bit_depth`
- `is_grayscale`
- `has_alpha`
- `file_size_bytes`
- `dpi_x`
- `dpi_y`
- `avg_luminance`
- `max_luminance`
- `luminance_std`
- `mean_r`
- `mean_g`
- `mean_b`
- `median_r`
- `median_g`
- `median_b`
- `exif_present`
- `iptc_present`
- `size_ok`
- `created_at`
- `updated_at`

`created_at` and `updated_at` are rendered with a trailing `Z` in the string returned by the API.

If `include_raw` is enabled, the same object also includes:

- `histogram_json`
- `exif_json`
- `iptc_json`

## Example response

```json
{
  "success": true,
  "data": {
    "image_uuid": "img-uuid",
    "image_variant": "orig",
    "width": 2048,
    "height": 1536,
    "format": "JPEG",
    "mode": "RGB",
    "bit_depth": 8,
    "is_grayscale": false,
    "has_alpha": false,
    "file_size_bytes": 345678,
    "dpi_x": 300,
    "dpi_y": 300,
    "avg_luminance": 123.4,
    "max_luminance": 255,
    "luminance_std": 22.1,
    "mean_r": 120.0,
    "mean_g": 121.0,
    "mean_b": 119.0,
    "median_r": 118.0,
    "median_g": 119.0,
    "median_b": 117.0,
    "exif_present": true,
    "iptc_present": false,
    "size_ok": true,
    "created_at": "2026-04-30T12:00:00Z",
    "updated_at": "2026-04-30T12:01:00Z"
  },
  "cached": false
}
```

## Notes

- The GET route returns `cached: true` only when the in-process cache contains a dictionary for the exact `image_uuid`, `variant`, and `include_raw` combination.
- The POST route always returns `cached: false`; it uses `updated` to indicate whether extraction/upsert ran.
- Both routes are scope-aware and resolve images only if the current user can see them.
