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
- `brightness`
- `contrast`
- `saturation`
- `red_luminance`
- `red_saturation`
- `green_luminance`
- `green_saturation`
- `blue_luminance`
- `blue_saturation`
- `gamma`
- `black_point`
- `white_point`
- `shadow_lift`
- `flattening`
- `invert`
- `filter`

Example:

```json
{
  "1": {
    "id": 7,
    "name": "Calibrated red-free",
    "brightness": 1.0,
    "contrast": 1.0,
    "saturation": 1.0,
    "red_luminance": 1.0,
    "red_saturation": 1.0,
    "green_luminance": 1.0,
    "green_saturation": 1.0,
    "blue_luminance": 1.0,
    "blue_saturation": 1.0,
    "gamma": 1.0,
    "black_point": 0.0,
    "white_point": 1.0,
    "shadow_lift": 0.0,
    "flattening": 0.0,
    "invert": false,
    "filter": "none"
  }
}
```

## `POST /api/viewer/presets/<int:slot_number>`

Valid slot numbers are `1` through `5`. The route creates or replaces the preset for that slot.

Body fields:

- `name`
- `brightness`
- `contrast`
- `saturation`
- `red_luminance`
- `red_saturation`
- `green_luminance`
- `green_saturation`
- `blue_luminance`
- `blue_saturation`
- `gamma`
- `black_point`
- `white_point`
- `shadow_lift`
- `flattening`
- `invert`
- `filter`

The seven color-tuning values use `1.0` as neutral and are clamped to
`0.0-3.0`. They are stored per preset so a grader can fine-tune overall
saturation and each RGB channel's luminance and saturation without altering the
source image.

Clinical enhancement values are display parameters only. The browser computes
an image-specific histogram from the decoded JPEG/PNG, applies conservative
auto-windowing, and runs the selected channel/levels/gamma/spatial enhancement
pipeline in WebGL. The server continues to serve the original image and stores
only the user's preset parameters. `none` is the exact decoded capture view;
software RGB channel views are simulations and are not labelled as optical
multispectral or true red-free acquisition.

Clinical tuning ranges are: `gamma` `0.35-2.5`, `black_point` `-0.2-0.25`,
`white_point` `0.5-1.2`, and `shadow_lift` and `flattening` `0-1`.

Highlight protection and the small fixed spatial enhancement used by RF/RF+
are implementation details of those validated modes, not grader-adjustable or
persistent preset fields. Local contrast, denoise, and sharpen controls are not
exposed because they can introduce halos, obscure small lesions, or amplify
JPEG artefacts.

Preset `filter` accepts only the routine clinical views: `none`, `enhance`,
`redfree`, or `redfreeenhanced`. Unknown values are coerced to `none`.
`enhance` uses the legacy luminance-masked shadow curve; `shadow_lift` controls
its strength and can also be combined deliberately with a red-free view.

Viewport zoom, pan, loupe size, loupe magnification, and loupe visibility are
session controls rather than preset fields. They are ignored when submitted to
the preset endpoint and are not returned by the preset endpoint. Applying or
fine-tuning a preset therefore leaves the current viewport unchanged.

## `DELETE /api/viewer/presets/<int:slot_number>`

Deletes the preset for the current user and slot if it exists.
