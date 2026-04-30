# Database Export and Restore

This page documents the database export and restore tooling.

## Routes

- `GET /admin/database-dump`
- `POST /admin/database-dump`
- `GET /admin/database-info`
- `GET /admin/database-excel-export`
- `POST /admin/database-excel-export`
- `GET /admin/database-tables`
- `GET /admin/database-restore/`
- `POST /admin/database-restore/upload`
- `POST /admin/database-restore/restore`

## Database dump

### `GET /admin/database-dump`

HTML page.

Auth:
- `@roles_required("admin")`
- `requires_reauth("database_dump")`

### `POST /admin/database-dump`

CSRF:
- Required via form token

Behavior:
- Dumps PostgreSQL with `pg_dump` or falls back to an SQLAlchemy-generated SQL dump
- SQLite uses `sqlite3 .dump`
- On success returns a gzipped file download

Success response:
- `200 OK`
- `Content-Type: application/gzip`
- attachment filename like `database_dump_YYYYMMDD_HHMMSS.sql.gz`

Failure:
- Redirect back to the form with flash messages

### `GET /admin/database-info`

Response `200`:
```json
{
  "database_type": "PostgreSQL",
  "database_size": "123 MB",
  "supports_dump": true
}
```

Response `500`:
```json
{ "error": "Database URL not configured" }
```

## Database Excel export

### `GET /admin/database-excel-export`

HTML page.

Auth:
- `@roles_required("admin")`
- `requires_reauth("database_excel_export")`

### `POST /admin/database-excel-export`

CSRF:
- Required

Request form fields:
- `tables` repeated list of table names

Success:
- `200 OK`
- `Content-Type: application/zip`
- attachment filename like `database_export_YYYYMMDD_HHMMSS.zip`

Failure:
- Redirect back to the page with flash messages

### `GET /admin/database-tables`

Response `200`:
```json
{
  "tables": [
    { "name": "users", "row_count": 10 }
  ],
  "total_tables": 1
}
```

Response `500`:
```json
{ "error": "Internal server error" }
```

## Database restore

### `GET /admin/database-restore/`

HTML restore page.

Auth:
- `@login_required`
- `@roles_required("admin")`

### `POST /admin/database-restore/upload`

Request:
- multipart form upload with `file`

Accepted extensions:
- `.sql`
- `.gz`
- `.zip`

Response `200`:
```json
{
  "success": true,
  "filename": "backup.sql",
  "file_size": 12345,
  "preview": {
    "total_users": 0,
    "new_users": 0,
    "existing_users": 0,
    "new_users_list": [],
    "conflicts_list": []
  }
}
```

Known errors:
- `400 {"error":"No file selected"}`
- `400 {"error":"Invalid file type. Allowed types: .sql, .sql.gz, .zip"}`
- `400 {"error":"File too large. Maximum size: 100MB"}`
- `400 {"error":"Failed to process file. Please check the logs."}`
- `500 {"error":"Upload failed. Please check the logs."}`

### `POST /admin/database-restore/restore`

Request JSON:
```json
{ "confirm_restore": true }
```

Behavior:
- Uses the uploaded file path stored in session
- Refuses to proceed unless `confirm_restore` is true

Success `200`:
```json
{
  "success": true,
  "message": "Database restored successfully",
  "note": "All data including user accounts has been restored from backup"
}
```

Known errors:
- `400 {"error":"No file uploaded or session expired"}`
- `400 {"error":"Restore not confirmed"}`
- `500 {"error":"Database restore failed - see server logs for details"}`

## CSRF Rules

- The dump and Excel export forms require CSRF.
- The restore upload flow is a standard browser upload and is CSRF-protected by the page.
- The JSON restore request still comes from the browser session and should be sent with the page CSRF token if invoked from JS.
