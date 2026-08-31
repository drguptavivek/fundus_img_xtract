# Analytics APIs

These endpoints power analytics dashboards and client-side charts.

## `GET /analytics/api/hospital-dashboard/disease-view`
## `GET /analytics/api/hospital-dashboard/lab-disease-view`
## `GET /analytics/api/hospital-dashboard/user-view`
## `GET /analytics/api/hospital-dashboard/roster-view`
## `GET /analytics/api/hospital-dashboard/encounter-view`

Returns scoped dashboard data for the authenticated user’s lab units.

Auth:
- `admin`, `local_admin`, `data_manager`, `analytics_viewer`

Response:
- JSON payload with a `data` array and metadata such as `lab_unit_scope_count`

Query params:
- `disease_id`
- `lab_unit_id`
- `hospital_id`

## `POST /analytics/model-performance/threshold-explorer`

Runs threshold analysis for the model performance page.

Common errors:
- missing or invalid numeric threshold inputs
- missing `disease_id` or `ai_model_id`
- no cases available for the selected filters

## Page routes with related JSON behavior

- `GET /analytics/images`
- `GET /analytics/encounters`
- `GET /analytics/encounter/view/<int:encounter_id>`

These are analytics page routes used by the browser UI. If a route returns JSON, document the exact payload beside the page route in the module docs that own it.

## Notes

- The hospital dashboard endpoints are the primary JSON contract for charts and summaries.
- KPI dataframe and export APIs are documented in `docs/API/kpis/`.
