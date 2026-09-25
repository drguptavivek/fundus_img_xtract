# Project EncounterSet Export API

This API powers the **Project Export** tab at `/projects/<project_id>/export`.
It produces non-PII exports for EncounterSets in the caller's active project
and Lab Unit scope.

## Authorization and privacy

- Login is required.
- The caller must hold an active `data_manager` project grant, or be a system
  administrator.
- Project-scoped grants cover configured Lab Units in the project. Lab-scoped
  grants cover only their configured Lab Unit.
- The worker repeats authorization when the job runs. Revoked access stops the
  export.
- Patient names, source upload filenames, grader identity, and free-text
  grade comments are excluded. Images are renamed to `<image_uuid>.<ext>`.
- The `Encounters` sheet includes the sorted union of browser-visible patient
  and encounter metadata columns. Name, contact, address, date-of-birth, and
  filename-bearing fields are retained as columns with masked values; internal
  upload metadata is omitted.
  Opaque upstream fields containing `raw_metadata` are omitted entirely because
  their nested payloads may contain PII.
  MRN, patient ID, and `hospital_UHID` are retained as permitted non-PII
  linkage fields.

## Filters

- `date_from`: optional inclusive EncounterSet capture date, ISO `YYYY-MM-DD`.
- `date_to`: optional inclusive EncounterSet capture date, ISO `YYYY-MM-DD`.
- `grading_filter`:
  - `all`: all scoped EncounterSets;
  - `any_graded`: at least one saved Grade row on any encounter/image task;
  - `completed`: at least one task exists and every encounter/image task is
    in `final` state.

## `GET /api/projects/<project_id>/exports/preview`

Returns the matched EncounterSet, image, and task counts. It also returns
`image_export_limit: 250` and whether the filtered result can be exported with
images. The 250 limit counts EncounterSets, not images.

## `POST /api/projects/<project_id>/exports`

CSRF is required through `X-CSRFToken`.

JSON request:

```json
{
  "kind": "workbook",
  "date_from": "2026-09-01",
  "date_to": "2026-09-30",
  "grading_filter": "any_graded"
}
```

`kind` is `workbook` or `images`. A successful request returns `202` with a
job token and status-page URL. An image request matching more than 250
EncounterSets returns `400` and must be narrowed; workbook exports have no
EncounterSet count limit.

The workbook contains `Encounters`, `Images`, `Tasks`, `Grade Submissions`,
and `Final Grades` sheets. Partial grading submissions remain present even if
the task has not reached `final`. `Final Grades` contains every task and marks
whether a persisted consensus/final grade exists, so unresolved tasks are not
silently omitted.

The `Encounters` sheet includes the core `patient_id` plus MRN and hospital
UHID metadata when available. These stable project identifiers support joins
to other research datasets.

## `GET /api/projects/<project_id>/exports/recent`

Returns up to 10 recent project-export jobs created by the current user. Each
row includes status and status-page URL. Completed jobs also include artifact
names and authorized download URLs. Jobs created by other users are excluded.

The image export includes numbered ZIP files, native annotations,
multi-annotator JSONL, IITK `aiims-eom-v1` JSONL, COCO JSONL, and standard
COCO JSON. ZIP paths use
`EncounterSets/<encounter_uuid>/<image_uuid>.<ext>` with adjacent sidecars.

## `GET /api/projects/<project_id>/exports/<job_token>/<filename>`

Downloads a completed artifact. The request repeats project export authority,
requires the job to belong to the current user and project, and rejects unsafe
filenames. Invalid or unauthorized requests return `404`.
