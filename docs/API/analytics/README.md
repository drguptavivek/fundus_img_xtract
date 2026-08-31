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

## Public dashboard APIs

### `GET /api/analytics/kpi`

Returns the public homepage and `/analytics` summary payload. Authentication and
CSRF are not required because this is a read-only public endpoint.

The `data.summary` object includes total images, encounters, tasks, gradings,
AI gradings, graders, models, and medical reports. `data.image_types` separates
the mutually exclusive physical image sources:

- `Direct`: non-pregraded rows from `direct_image_uploads`
- `Pregraded`: pregraded rows from `direct_image_uploads`
- `ZIP`: classical `encounter_files` images
- `EncounterSet`: physical `encounter_set_images` rows

`summary.total_images` is the sum of those four source counts. EncounterSet
verification uses the parent encounter verification status. `summary.total_encounters`
includes both classical and set-based `patient_encounters` rows.

`data.report_stats` includes the existing DR and glaucoma report counts plus
`encounter_set_pdfs`, `reviewed_encounter_set_pdfs`, and their combined
`total_reports`. EncounterSet PDFs are attachments whose `asset_kind` is `pdf`
or whose MIME type is `application/pdf`.

Example response excerpt:

```json
{
  "success": true,
  "data": {
    "summary": {
      "total_images": 20672,
      "total_encounters": 3764,
      "encounter_set_pdfs": 1121,
      "total_reports": 4352
    },
    "image_types": {
      "Direct": {"total": 110},
      "Pregraded": {"total": 5425},
      "ZIP": {"total": 6365},
      "EncounterSet": {"total": 8772}
    }
  }
}
```

### `GET /api/analytics/chart-data`

Returns `data.upload_trends` and `data.grading_trends` for the last 12 months.
Upload trend rows include `direct`, `pregraded`, `zip`, and `encounter_set`
counts. Grading trends include tasks backed by EncounterSet images as well as
direct and classical encounter-file images. Authentication and CSRF are not
required.

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
