# Direct Files KPI API

These endpoints power the direct-upload analytics page and exports.

## Routes

- `GET /api/kpis/direct-files/filtered-dataframe`
- `GET /api/kpis/direct-files/filtered-dataframe-excel`
- `GET /api/kpis/direct-files/upload-metrics`

## Shared auth and filters

Auth:
- `@login_required`
- `@roles_required("admin", "data_manager")`

Query params:
- `start_date` in `YYYY-MM-DD`
- `end_date` in `YYYY-MM-DD`
- `hospital_ids` comma-separated integers
- `lab_unit_ids` comma-separated integers
- `page` optional on the filtered dataframe endpoint, default `1`
- `length` optional on the filtered dataframe endpoint, default `25`

Validation:
- Invalid dates or ID lists return a JSON error payload with HTTP `400`

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

## `GET /api/kpis/direct-files/filtered-dataframe`

Response data keys:
- `period`
- `total_records`
- `returned_records`
- `truncated_count`
- `data`
- `columns`
- `recordsTotal`
- `recordsFiltered`

The endpoint server-side paginates the filtered dataframe and returns only the selected page.

## `GET /api/kpis/direct-files/filtered-dataframe-excel`

Response:
- `200 OK` Excel file download
- MIME type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

The workbook includes:
- `Encounter Data`
- `Filters Applied`

## `GET /api/kpis/direct-files/upload-metrics`

Response data keys:
- `total_uploads`
- `verified_count`
- `task_count`
- `grading_count`
- `by_hospital`
- `by_lab_unit`
- `by_camera`
- `by_disease`
- `by_area`
- `mydriatic_breakdown`
- `pregraded_breakdown`
- `task_status_breakdown`
- `grading_role_breakdown`
- `pregraded_percentage`
- `verification_percentage`
- `task_completion_percentage`
- `grading_completion_percentage`
- `daily_uploads`
- `period`

`by_*` sections are arrays of grouped counts.

## CSRF Rules

- These routes are `GET` only.
- No CSRF token is required.
