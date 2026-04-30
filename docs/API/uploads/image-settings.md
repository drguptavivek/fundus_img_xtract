# Image Settings and Metadata API

This page documents the viewer settings and image metadata APIs consumed by the image viewer and JS tooling.

## `GET /api/viewer/settings`

Returns the current user’s viewer settings.

Response fields:
- loupe size/zoom/enabled
- zoom
- pan offsets
- brightness
- contrast
- filter

## `POST /api/viewer/settings`

Saves the current user’s viewer settings.

Request body:
- JSON object with any subset of the supported settings fields

Common errors:
- missing JSON body
- internal server error

## `GET /api/viewer/presets`

Returns the current user’s saved viewer presets.

## `POST /api/viewer/presets/<slot_number>`

Creates or updates one preset slot.

Validation:
- slot number must be between 1 and 5
- request body must be JSON

## `DELETE /api/viewer/presets/<slot_number>`

Deletes one preset slot.

## `GET /api/image-metadata/<image_uuid>`

Returns metadata for one image.

Query params:
- `variant`
- `include_raw`

Common errors:
- image not found
- metadata not found

## `POST /api/image-metadata/<image_uuid>`

Extracts or refreshes metadata for one image.

Request body:
- `variant`
- `include_raw`
- `force`

Common errors:
- image not found
- metadata extraction failed
