# Encounter Set Upload API

This is the upload contract for encounter-set ingestion and the project-scoped upload mapping flow.

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
- `disease_id`
- `spatial_position`
- file upload payload

Important validation:
- upload scope is validated against the current user’s permitted lab units and the project/mapping rules
- the encounter must belong to the selected project

Common errors:
- missing or invalid project/lab/disease context
- invalid image file
- access denied
- encounter belongs to a different project

## Notes

- This is the main contract to document for the project-scoped upload mapping system because uploads are accepted only when the caller’s project/lab/disease scope matches the server-side mapping source of truth.
