# Encounter Task Results Export

This endpoint downloads filtered encounter-linked grading data as XLSX. It exports data only; image files are not included.

## Authorization

Allowed roles:

- `admin`
- `local_admin`
- `data_manager`

The export includes patient identifiers and OCR fields because it is intended for clinical-data linkage. Hospital and lab-unit scoping is still enforced from the current user.

## Filters

Accepted query parameters:

- `hospital_id`: optional integer hospital ID.
- `lab_unit_id`: optional integer lab-unit ID.
- `start_date`: optional `YYYY-MM-DD` capture-date lower bound.
- `end_date`: optional `YYYY-MM-DD` capture-date upper bound.
- `project_id`: optional repeated integer project ID. Include multiple `project_id` parameters to export multiple named projects.
- `include_classical`: optional `1` to include legacy/classical encounters where `patient_encounters.project_id` is null.

When no `project_id` or `include_classical` parameter is sent, the export includes all matching sources in scope. When either source parameter is sent, only the selected named projects and/or selected classical encounters are exported. The export includes all matching encounters in scope, not only the current paginated page.

## Download

`GET /api/analytics/encounters/export/task-results.xlsx`

Response: XLSX file download.

Sheets:

- `Image Task Results`: one row per image-linked disease grading task from the disease-specific materialized views. If an image has tasks for two diseases, it has two rows. Columns include project/classical source fields, resident, resident2, arbitrator, review, AI model grades, consensus, and regrade-adjudicator grade aggregates joined from `grades.role_slot = 'regrade_adj'`.
- `Encounter OCR Data`: one row per encounter with project/classical source fields, patient identifiers, verification statuses, flattened DR OCR columns, and flattened cleaned glaucoma OCR columns.

Example:

```bash
curl -L -o encounter_task_results.xlsx \
  "https://eyeimg.aiims.edu.in/api/analytics/encounters/export/task-results.xlsx?start_date=2026-07-01&end_date=2026-07-22&include_classical=1&project_id=4&project_id=9"
```

## CSRF

This is a `GET` download endpoint and does not require a CSRF token.
