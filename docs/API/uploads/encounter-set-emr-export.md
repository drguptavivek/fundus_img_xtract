# EncounterSet EMR Export

Downloads the PII-enabled EncounterSet browser data for one project and capture month as a flat XLSX workbook. The export is intended for reconciliation against an EMR.

## Endpoint

`GET /api/encounter-sets/export.xlsx`

Required query parameters:

- `project_id`: integer project ID.
- `month`: capture month in `YYYY-MM` format.

Example:

```bash
curl -L -o encountersets.xlsx \
  "https://eyeimg.aiims.edu.in/api/encounter-sets/export.xlsx?project_id=3&month=2026-07"
```

## Authorization and scope

Allowed roles are `admin`, `local_admin`, `data_manager`, `fileUploader`, and `optometrist`. The same hospital and lab-unit `upload` scope used by the PII EncounterSet browser is enforced. The no-PII collaborator browser does not expose this export.

The endpoint is a `GET` download and does not require a CSRF token. The response uses `Cache-Control: no-store` because the workbook contains patient identifiers.

## Workbook contract

The workbook contains one `EncounterSet EMR Data` sheet and one row per matching EncounterSet, ordered by capture date and encounter ID. It includes:

- Encounter ID/type, hospital UHID, patient demographics, Remidio site identifier, and clinical image count.
- Capture date plus capture time converted to the requesting user's configured timezone (or the application display timezone when the user has none).
- DR, glaucoma, and AMD PDF-presence flags based on disease evidence in EncounterSet PDF attachment metadata.
- Every persisted column from DR, AMD, raw glaucoma, and cleaned glaucoma OCR tables. Multiple OCR rows use indexed prefixes such as `dr_ocr_1_`, `amd_ocr_2_`, `glaucoma_ocr_1_`, and `glaucoma_cleaned_ocr_1_` so data is not overwritten.

All EncounterSet sources are included. Remidio API rows use nested Remidio patient/encounter metadata and linked exam data. IITK and other non-Remidio rows use their flat age, gender, and start-time metadata when present, then fall back to the core encounter patient ID, name, and capture date. Source-specific values that were never collected remain blank.

Validation errors return JSON with HTTP 400:

```json
{"error": "month must use YYYY-MM format"}
```
