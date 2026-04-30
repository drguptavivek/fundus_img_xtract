# Lookup APIs

These endpoints expose reference data for clients that need hospitals, lab units, diseases, or grading metadata.

## `GET /api/hospitals`

Returns the list of hospitals visible to the current user.

## `GET /api/hospitals/<hospital_id>`

Returns one hospital record.

Common errors:
- `404` when the hospital is not found or is not visible to the caller

## `GET /api/hospitals/<hospital_id>/labunits`

Returns lab units for one hospital.

## `GET /api/labunits`

Returns lab units visible to the current user.

## `GET /api/labunits/<lab_unit_id>`

Returns one lab unit record.

## `GET /api/disease-grades/<disease_id>`

Returns grading options for one disease.

## `GET /api/diseases-with-gradings`

Returns all diseases with their grading options.

## `GET /api/diseases-gradings-features/<disease_id>`

Returns disease grading features for the specified disease.

## `GET /api/grading-eligibility/users/<user_id>`

Returns grading eligibility for a user.

## `GET /api/grading-eligibility/users/<user_id>/details`

Returns grouped eligibility details for a user.

## `GET /api/admin/users`

Returns paginated user activity for admin dashboards.

Auth:
- `admin` or `data_manager`

Response:
- JSON when requested as JSON
- HTML fragment when requested with HTMX or `format=html`
