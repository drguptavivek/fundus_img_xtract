# Analytics API Surface

This folder documents the analytics pages and JSON endpoints.

## Pages and dashboards

- [Hospital Dashboard](hospital-dashboard.md)
- [Model Performance](model-performance.md)
- [Encounter Task Results Export](encounter-task-results-export.md)

## Media and KPI pages

- `GET /analytics/images`
- `GET /analytics/encounters`
- `GET /analytics/encounter/view/<int:encounter_id>`
- `GET /analytics/direct/view/<string:uuid_str>`

## File download APIs

- `GET /api/analytics/encounters/export/task-results.xlsx`

## Public dashboard API

The lightweight public and mobile contract is documented under
[Public KPI API](../public-analytics/README.md). The retired
`/api/analytics/kpi` and `/api/analytics/chart-data` endpoints are not part of
the current API surface.

## Dataset curation

- `GET /analytics/dataset-curation`
- `POST /analytics/dataset-curation`
- `GET /analytics/dataset-curation/<dataset_uuid>`
- `POST /analytics/dataset-curation/<dataset_uuid>`
- `GET /analytics/dataset-curation/<dataset_uuid>/viewer/<string:image_uuid>`
- `GET /analytics/dataset-curation/<dataset_uuid>/screen-gallery`
- `GET /analytics/dataset-curation/<dataset_uuid>/screen-list`
- `POST /analytics/dataset-curation/<dataset_uuid>/toggle-item`
- `POST /analytics/dataset-curation/<dataset_uuid>/add-more`
- `POST /analytics/dataset-export/<dataset_uuid>`
- Dataset sharing is managed by the canonical `POST /datasets/share` endpoint.
- `POST /analytics/dataset-curation/<dataset_uuid>/finalize`
- `POST /analytics/dataset-curation/<dataset_uuid>/unfinalize`
- `GET /analytics/dataset-export/<job_token>/<path:filename>`
- `POST /analytics/dataset-curation/<dataset_uuid>/delete`

The dataset-curation routes are page workflows and are documented elsewhere only at a high level.

Dataset visibility or curation does not authorize export. A masked classical
export requires `data_exporter` over every included task; a project export
requires `data_exporter` or the direct `pii_exporter` grant over every included
task. Admin is break-glass for role scope only: missing, mixed, wrong-disease,
wrong-Lab-Unit, or wrong-project task lineage still denies. Queueing, worker
execution, regeneration, and private artifact download re-evaluate current
authority. Public signed-share downloads retain their separate exact
share/token/OTP contract.

## Contract Notes

- The hospital dashboard JSON is the primary analytics API contract.
- KPI dataframe/export APIs are documented in `docs/API/kpis/`.
- Most analytics pages are `GET` HTML routes with no CSRF. Mutating dataset curation POSTs are CSRF protected in the templates.
