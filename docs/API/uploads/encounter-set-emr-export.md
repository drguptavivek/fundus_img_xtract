# EncounterSet EMR Export

Downloads the EncounterSet browser data for one project and capture month as a flat XLSX workbook. The export is intended for reconciliation against an EMR and for correlating EncounterSets with other data sources.

## Endpoints

- `GET /api/encounter-sets/export.xlsx`: masked workbook. Identifier columns (patient name, UHID, patient ID, custom identifiers, file names, remarks) are replaced with `Anonymous`/`masked`. This is the "Export month" button in the EncounterSet browser.
- `GET /api/encounter-sets/export-pii.xlsx`: identifier-bearing workbook with the same columns unmasked. Requires the `pii_exporter` project role (or admin) and recent re-authentication.

Query parameters:

- `project_id`: integer project ID (required for project-scoped exports).
- `month`: capture month in `YYYY-MM` format. Omit it (or pass it empty) to export every month for the project; the download is then named `..._all-months_...xlsx`. The browser exposes this as the "Export all months" button next to "Export month".
- `lab_unit_id`: optional integer lab unit ID to narrow the export to one lab unit.

Example:

```bash
curl -L -o encountersets.xlsx \
  "https://eyeimg.aiims.edu.in/api/encounter-sets/export.xlsx?project_id=3&month=2026-07"

# every month for the project
curl -L -o encountersets_all.xlsx \
  "https://eyeimg.aiims.edu.in/api/encounter-sets/export.xlsx?project_id=3"
```

## Authorization and scope

The masked export requires the `data_exporter` or `pii_exporter` project role (or admin); the PII export requires `pii_exporter` (or admin). Rows are limited to the lab units the user may export from. The no-PII collaborator browser does not expose this export.

Both endpoints are `GET` downloads and do not require a CSRF token. Responses use `Cache-Control: no-store`.

## Workbook contract

The workbook contains one `EncounterSet EMR Data` sheet and one row per matching EncounterSet, ordered by capture date and encounter ID. It includes:

- Encounter ID/type, hospital UHID, patient demographics, Remidio site identifier, and clinical image count.
- Capture date plus capture time converted to the requesting user's configured timezone (or the application display timezone when the user has none).
- DR, glaucoma, and AMD PDF-presence flags based on disease evidence in EncounterSet PDF attachment metadata.
- Every persisted column from DR, AMD, raw glaucoma, and cleaned glaucoma OCR tables. Multiple OCR rows use indexed prefixes such as `dr_ocr_1_`, `amd_ocr_2_`, `glaucoma_ocr_1_`, and `glaucoma_cleaned_ocr_1_` so data is not overwritten.
- EncounterSet metadata columns, appended after the OCR columns. Every key shown in the browser's patient and encounter metadata panels is exported as `metadata_patient_<key>` or `metadata_encounter_<key>` (for example `metadata_patient_site_recruitment`, `metadata_encounter_mode_capture`, `metadata_encounter_eye_laterality`, `metadata_encounter_patient_diagnosis_other`, `metadata_encounter_captured_positions`, `metadata_encounter_source_session_id`). Flat top-level metadata keys used by IITK ZIP imports are exported as `metadata_<key>` (for example `metadata_age`, `metadata_gender`, `metadata_mode`). The column set is the sorted union across all exported rows; rows without a key are blank. List values such as `captured_positions` are comma-joined. The internal `upload` section is not exported. In the masked export, metadata columns whose names contain identifier markers (for example `metadata_patient_hospital_UHID`) are masked like the base columns.

All EncounterSet sources are included. Remidio API rows use nested Remidio patient/encounter metadata and linked exam data. IITK and other non-Remidio rows use their flat age, gender, and start-time metadata when present, then fall back to the core encounter patient ID, name, and capture date. Source-specific values that were never collected remain blank.

Validation errors return JSON with HTTP 400:

```json
{"error": "month must use YYYY-MM format"}
```
