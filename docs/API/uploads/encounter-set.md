# Encounter Set Upload API

This is the upload contract for encounter-set ingestion and the project-scoped upload profile flow.

## `GET /api/v1/encounter-set/unverified`

Lists set-based encounters that still need verification.

Auth:
- `admin`, `local_admin`, `optometrist`

Response:
- JSON array of encounter summaries

## `GET /api/v1/encounter-set/<uuid>/details`

Returns the encounter-set details for one encounter bundle.

Response:
- encounter metadata
- image list
- status fields

## `POST /api/v1/encounter-set/image/<uuid>/position`

Updates the grid position for one encounter-set image.

Required JSON:
- `spatial_position`

Common errors:
- missing position
- invalid position
- image not found
- access denied

## `POST /api/v1/encounter-set/upload`

Uploads one image into an encounter set.

Required inputs:
- `lab_unit_id`
- `project_id`
- `upload_profile_id` or `profile_id`
- `spatial_position`
- `camera_id`
- `area_id`
- file upload payload

Important validation:
- upload scope is validated against the current user's assigned profile, permitted lab unit, project, disease, camera/site, and mydriatic rules
- the encounter must belong to the selected project/profile
- target diseases are stored on the encounter; they cannot change after upload starts

Common errors:
- missing or invalid project/lab/disease context
- invalid image file
- access denied
- encounter belongs to a different project

## Notes

- This is the main contract to document for project-scoped upload profiles because uploads are accepted only when the caller's project/lab/disease/camera/site scope matches the server-side profile source of truth.
