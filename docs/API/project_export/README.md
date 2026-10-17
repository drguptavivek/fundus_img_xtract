# Project export package (DuckDB) API

Admin download (role `admin`) of a staged export package: one `.duckdb` file with typed tables, a `manifest`,
a `data_dictionary` and a structure `guide`. Image and PDF files are never included, only references.

All endpoints: `GET`, session auth, role `admin`, no CSRF token needed (read-only).
Downloads additionally require a recent password confirmation (`/auth/confirm-password`; the browser is
redirected and returns to the same URL), are limited to 6 per hour, and are written to the sensitive-operations
audit log (`project_duckdb_export`: initiated / completed with SHA-256 / failed).

## `GET /api/admin/project-export/options`
Choices for the export form.
```json
{"projects":[{"id":3,"code":"ICMR-VG","title":"Integrated DR Glaucoma Screening","active":true}],
 "hospitals":[{"id":1,"name":"AIIMS"}],
 "lab_units":[{"id":1,"name":"Community Ophthalmology","hospital_id":1}]}
```

## `GET /api/admin/projects/<project_id>/export.duckdb`
Package for one project (all of its active lab units).

| Query | Meaning |
|---|---|
| `identifiers=1` | Include patient id/name and original file names. Default: withheld. |

## `GET /api/admin/no-project/export.duckdb`
Package for encounters that belong to **no project**.

| Query | Meaning |
|---|---|
| `hospital_id` (repeatable) | Hospitals; alone, means all of their lab units. |
| `lab_unit_id` (repeatable) | Lab units; when hospitals are also given, labs must belong to them. |
| `identifiers=1` | As above. |

At least one `hospital_id` or `lab_unit_id` is required.

## Excel
`GET /api/admin/projects/<project_id>/export.xlsx` and `GET /api/admin/no-project/export.xlsx` take the same parameters
and return a workbook **generated from the DuckDB package** (one sheet per table, guide sheets first). Excel limits are
handled, not hidden: cells over 32,000 characters are truncated, tables over 1,048,575 rows are cut, list/object values
become JSON text, timestamps are UTC without a zone, and every such case is listed on the last sheet, `xlsx_notes`.
DuckDB is the complete package.

## Responses
* `200` attachment `project_<code>[_identifiers]_<UTC timestamp>.duckdb` (`Cache-Control: no-store`).
* `400 {"error":"invalid", ...}` bad ids, nothing selected, or the selection matches no lab units.
* `401/302` password confirmation needed; `403` not an admin; `404 {"error":"not_found"}` unknown project;
  `429` rate limited; `503 {"error":"unavailable"}` the DuckDB engine is not installed on this server.

## Example
```bash
curl -b cookies.txt -OJ "https://HOST/api/admin/no-project/export.duckdb?hospital_id=1&hospital_id=2&lab_unit_id=5"
duckdb project_x.duckdb "select * from manifest"
```

The admin page is `/admin/project-export` (menu: Admin > Integrations > Project Data Export); HTMX loads the
form fragment and the form submits a plain GET to the endpoints above (a file download cannot be HTMX-swapped).
Module: `project_export/` (`schema.py` is the table contract and the source of the data dictionary).

## Access and identifiers
Only the `admin` role may use these endpoints; there is no separate superadmin tier. Identifiers (`identifiers=1`) are an
explicit opt-in per download, off by default, re-confirmed with the admin's password and audited. The lab-scoped
`local_admin` ("Site Admin") role has no access yet; it is a possible follow-up (own hospital/lab units only, always PII-filtered).

## Package contents (schema version 1)
Source of truth: `project_export/schema.py` (every table and column, generated into the `data_dictionary` table).

| Stage | Tables |
|---|---|
| package | `manifest`, `data_dictionary`, `guide` (how to read the file + runnable example queries), `relationships` (joins) |
| creation | `encounters`, `images`, plus typed flattened copies `encounter_metadata` and `image_metadata_values` |
| api_metadata | `api_exams`, `api_images`, `api_reports` (original Remidio API data), `iitk_sessions` |
| verification | `verification_encounters`, `verification_images` (effective vs original laterality, gradability and reasons), `verification_history` |
| ocr | `ocr_reports` |
| remote_ai | `ai_runs` (task-level and encounter-level), `ai_image_results`, `ai_target_results` |
| tasks / grades | `tasks`, `grades` (all roles incl. AI and AI-review fields), `consensus` |
| annotations | `coco_annotations` (one row per annotation instance, image fields repeated), `coco_categories`, `coco_images` (incl. images without annotations) |
| grading_timing | `grading_sessions`, `grading_session_targets` (hold_seconds is an upper bound; `submitted` holds are real work) |
| discrepancy_review | `review_history`, `regrade_tasks`, `review_corrections` |
| intra_rater | `intra_rater_batches`, `intra_rater_tasks`, `intra_rater_grades` |
| lookup | `dim_lab_units`, `dim_grade_labels`, `dim_ai_models` |

Rules: no image/PDF files (references only); identifiers, MRN, file names and patient ids in payloads only with
`identifiers=1`; staff free text (remarks, observations, reasons, comments) exported as entered; images flagged by the
PII scan keep all their rows (`images.pii_detected`); project exports include every lab mapped to the project, active or not.
Without `identifiers=1` the provider payloads in the AI tables lose patient ids and file names, and file names are masked
in system error text. Intra-rater batches, tasks and grades are included (`intra_rater_*`). Not included: curated datasets, workbench drafts/tokens, image and PDF files.

Dependency: `duckdb==1.5.5` (pyproject `web` and `general` groups, `uv.lock`); the venv-builder image must be rebuilt
before the endpoints can build packages (until then they answer `503`). DuckDB 2.x is to be adopted once stable.
