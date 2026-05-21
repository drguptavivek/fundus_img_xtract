# Stuck Remidio Upload Cleanup

Operational JSON endpoints for processed Remidio ZIP intake files that remained
under `files/zip_upload_zips` after successful ingestion.

## Authorization

- Roles: `admin` or `data_manager`
- Authentication required
- `POST` requests require CSRF for browser callers.

## GET `/admin/stuck-remidio-uploads/status`

Returns a dry-run cleanup report. No files are moved. By default the scan covers
all ZIP intake date folders.

Query parameters:

- `date_folder`: optional intake folder name to narrow the scan, for example `2026_04_20`
- `limit`: optional max ZIP files to scan, default is no limit

Example response:

```json
{
  "success": true,
  "data": {
    "dry_run": true,
    "date_folder": "2026_04_20",
    "scanned": 98,
    "eligible": 98,
    "moved": 0,
    "skipped": 0,
    "errors": 0,
    "items": []
  }
}
```

## POST `/admin/stuck-remidio-uploads/cleanup`

Runs the guarded cleanup. By default this scans all ZIP intake date folders and
performs the move for eligible files; pass `"dry_run": true` to preview through
the mutation endpoint.

JSON body or form fields:

- `date_folder`: optional intake folder name to narrow the cleanup
- `limit`: optional max ZIP files to scan, default is no limit
- `dry_run`: optional boolean, default `false`

The cleanup only moves a ZIP when all checks pass:

- `zip_files.zip_filename` matches the cleaned ZIP filename
- A linked `patient_encounters` row exists
- At least one `encounter_files` or `encounter_file_pdfs` row exists
- No active `job_items` row exists for the original or cleaned ZIP filename

Files are moved into the matching `files/zips_upload_processed/<date_folder>/`
archive folder without overwriting existing files.
