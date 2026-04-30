# Viewer Settings API

These routes store per-user viewer state and named presets.

Auth and CSRF:

- `GET` routes require a logged-in session only.
- `POST` and `DELETE` routes require CSRF because they use the browser session.

## Routes

| Route | Method | Auth | Request | Response | Status codes |
| --- | --- | --- | --- | --- | --- |
| `/api/viewer/settings` | `GET` | Session + login | None | Viewer settings object | `500` on unexpected error. |
| `/api/viewer/settings` | `POST` | Session + login + CSRF | JSON object with any subset of settings fields | `{ "success": true }` | `400` when no JSON body is provided. `500` on unexpected error. |
| `/api/viewer/presets` | `GET` | Session + login | None | Object keyed by slot number (`1-5`) | `500` on unexpected error. |
| `/api/viewer/presets/<int:slot_number>` | `POST` | Session + login + CSRF | JSON preset fields | `{ "success": true }` | `400` when slot is outside `1-5` or the body is missing. `500` on unexpected error. |
| `/api/viewer/presets/<int:slot_number>` | `DELETE` | Session + login + CSRF | None | `{ "success": true }` | `400` when slot is outside `1-5`. `404` if the preset does not exist. `500` on unexpected error. |

## `GET /api/viewer/settings`

If no row exists for the current user, the route returns defaults from code:

```json
{
  "loupe_size": 200,
  "loupe_zoom": 2.0,
  "loupe_enabled": false,
  "zoom": 100,
  "pan_x": 0,
  "pan_y": 0,
  "brightness": 1.0,
  "contrast": 1.0,
  "filter": "none"
}
```

If a row exists, the same keys are returned from `ViewerSettings`.

## `POST /api/viewer/settings`

Only provided keys are updated. The implementation clamps values to these ranges:

- `loupe_size`: `100-500`
- `loupe_zoom`: `1.0-4.0`
- `zoom`: `40-500`
- `pan_x`: `-600-600`
- `pan_y`: `-600-600`
- `brightness`: `0.5-5.0`
- `contrast`: `0.5-5.0`

`filter` is accepted only if it is one of:

- `none`
- `redfree`
- `greenboost`
- `bluemono`
- `gray`
- `contrast`
- `enhance`

Invalid filters are coerced to `none`.

## `GET /api/viewer/presets`

Returns a dictionary keyed by slot number. Each slot value contains:

- `id`
- `name`
- `loupe_size`
- `loupe_zoom`
- `loupe_enabled`
- `zoom`
- `pan_x`
- `pan_y`
- `brightness`
- `contrast`
- `filter`

Example:

```json
{
  "1": {
    "id": 7,
    "name": "Low zoom",
    "loupe_size": 200,
    "loupe_zoom": 2.0,
    "loupe_enabled": false,
    "zoom": 100,
    "pan_x": 0,
    "pan_y": 0,
    "brightness": 1.0,
    "contrast": 1.0,
    "filter": "none"
  }
}
```

## `POST /api/viewer/presets/<int:slot_number>`

Valid slot numbers are `1` through `5`. The route creates or replaces the preset for that slot.

Body fields:

- `name`
- `loupe_size`
- `loupe_zoom`
- `loupe_enabled`
- `zoom`
- `pan_x`
- `pan_y`
- `brightness`
- `contrast`
- `filter`

## `DELETE /api/viewer/presets/<int:slot_number>`

Deletes the preset for the current user and slot if it exists.
