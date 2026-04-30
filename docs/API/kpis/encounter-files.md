# Encounter Files KPI API

These endpoints power the encounter-file analytics page and its exports.

## Routes

- `GET /api/kpis/encounter-files/filtered-dataframe`
- `GET /api/kpis/encounter-files/filtered-dataframe-excel`
- `GET /api/kpis/encounter-files/year-month-wise-uploads`
- `GET /api/kpis/encounter-files/dr-reports-count`
- `GET /api/kpis/encounter-files/glaucoma-reports-count`
- `GET /api/kpis/encounter-files/images-count`
- `GET /api/kpis/encounter-files/dr-results-distribution`
- `GET /api/kpis/encounter-files/glaucoma-results-distribution`
- `GET /api/kpis/encounter-files/vcdr-distribution`

## Shared auth and filters

Auth:
- `@login_required`
- `@roles_required("admin", "data_manager")`

Query params:
- `start_date` in `YYYY-MM-DD`
- `end_date` in `YYYY-MM-DD`
- `hospital_ids` comma-separated integers
- `lab_unit_ids` comma-separated integers

Validation:
- Invalid dates or ID lists return a JSON error payload with HTTP `400`
- `start_date` must not be after `end_date`

## Standard JSON envelope

Success:
```json
{
  "success": true,
  "data": {},
  "message": "Data retrieved successfully",
  "timestamp": "2026-04-30T12:00:00+00:00",
  "filters_applied": {}
}
```

Error:
```json
{
  "success": false,
  "error": "Invalid parameters",
  "message": "details"
}
```

## `GET /api/kpis/encounter-files/filtered-dataframe`

Response data keys:
- `period`
- `total_records`
- `data`
- `columns`

Each `data[]` row is the filtered encounter dataframe row after NaT/NaN normalization.

## `GET /api/kpis/encounter-files/filtered-dataframe-excel`

Response:
- `200 OK` Excel file download
- MIME type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

The workbook includes:
- `Encounter Data`
- `Filters Applied`

## `GET /api/kpis/encounter-files/year-month-wise-uploads`

Response data keys:
- `period`
- `summary`
- `monthly_data`

`summary` contains:
- `total_uploads`
- `total_captures`
- `total_dr_reports`
- `total_glaucoma_reports`
- `total_no_reports`

Each `monthly_data[]` row contains:
- `year`
- `month`
- `month_name`
- `uploads`
- `captures`
- `dr_reports`
- `glaucoma_reports`
- `no_reports`
- optional `hospital_id`, `hospital_name`, `lab_unit_id`, `lab_unit_name`

## `GET /api/kpis/encounter-files/dr-reports-count`

Response data keys:
- `period`
- `dr_reports.total`
- `dr_reports.percentage`
- `dr_reports.by_hospital`
- `dr_reports.by_lab_unit`

## `GET /api/kpis/encounter-files/glaucoma-reports-count`

Response data keys:
- `period`
- `glaucoma_reports.total`
- `glaucoma_reports.percentage`
- `glaucoma_reports.monthly_breakdown`
- `glaucoma_reports.by_hospital`
- `glaucoma_reports.by_lab_unit`

## `GET /api/kpis/encounter-files/images-count`

Response data keys:
- `total_encounters`
- `verified_images`
- `verification_rate`
- `by_lab_unit`

Each `by_lab_unit[]` row includes counts and a `verification_rate`.

## `GET /api/kpis/encounter-files/dr-results-distribution`

Response data keys:
- `distribution`
- `percentages`
- `monthly_trends`

## `GET /api/kpis/encounter-files/glaucoma-results-distribution`

Response data keys:
- `distribution`
- `percentages`

## `GET /api/kpis/encounter-files/vcdr-distribution`

Response data keys:
- `right_eye`
- `left_eye`

Each eye object contains:
- `mean`
- `median`
- `std_dev`
- `range.normal_0_5`
- `range.borderline_0_5_0_7`
- `range.abnormal_0_7_0_8`
- `range.severely_abnormal_gt_0_8`

## CSRF Rules

- These routes are `GET` only.
- No CSRF token is required.
