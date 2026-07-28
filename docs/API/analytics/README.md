# Analytics API Surface

This folder documents the analytics pages and JSON endpoints.

## Pages and dashboards

- [Hospital Dashboard](hospital-dashboard.md)
- [Model Performance](model-performance.md)
- [Encounter Task Results Export](encounter-task-results-export.md)

## Media and KPI pages

- `GET /analytics/encounter-files`
- `GET /analytics/direct-uploads/kpi`
- `GET /analytics/images`
- `GET /analytics/encounters`
- `GET /analytics/encounter/view/<int:encounter_id>`
- `GET /analytics/direct/view/<string:uuid_str>`

## File download APIs

- `GET /api/analytics/encounters/export/task-results.xlsx`

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
- `POST /analytics/dataset-curation/<dataset_uuid>/share`
- `POST /analytics/dataset-curation/<dataset_uuid>/finalize`
- `POST /analytics/dataset-curation/<dataset_uuid>/unfinalize`
- `GET /analytics/dataset-export/<job_token>/<path:filename>`
- `POST /analytics/dataset-curation/<dataset_uuid>/delete`

The dataset-curation routes are page workflows and are documented elsewhere only at a high level.

## Contract Notes

- The hospital dashboard JSON is the primary analytics API contract.
- KPI dataframe/export APIs are documented in `docs/API/kpis/`.
- Most analytics pages are `GET` HTML routes with no CSRF. Mutating dataset curation POSTs are CSRF protected in the templates.
