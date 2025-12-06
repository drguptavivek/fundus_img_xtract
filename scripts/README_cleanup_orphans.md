# Cleanup Scripts

This directory contains scripts for cleaning up various types of orphaned records and files in the fundus image management system.

## Available Scripts

### 1. `cleanup_orphaned_zip_files.py`
Cleans up orphaned ZIP file records that exist in the `zip_files` table but no longer have an associated `PatientEncounters` record.

**Usage:**
```bash
# Dry run (default) - shows what would be deleted without actually deleting
uv run python scripts/cleanup_orphaned_zip_files.py

# Execute - actually deletes the orphaned records
uv run python scripts/cleanup_orphaned_zip_files.py --execute

# Verbose output
uv run python scripts/cleanup_orphaned_zip_files.py --verbose
```

### 2. `cleanup_orphaned_records.py` (Comprehensive)
Cleans up all types of orphaned records:
- Orphaned ZIP file records
- Orphaned encounter file records (images)
- Orphaned PDF file records
- Orphaned DR and Glaucoma report records
- Also attempts to clean up associated files from disk

**Usage:**
```bash
# Dry run for all record types
uv run python scripts/cleanup_orphaned_records.py

# Execute cleanup for all record types
uv run python scripts/cleanup_orphaned_records.py --execute

# Clean up specific type only
uv run python scripts/cleanup_orphaned_records.py --type zip
uv run python scripts/cleanup_orphaned_records.py --type files
uv run python scripts/cleanup_orphaned_records.py --type pdfs
uv run python scripts/cleanup_orphaned_records.py --type reports

# Verbose output
uv run python scripts/cleanup_orphaned_records.py --verbose
```

## When to Use These Scripts

### After Deleting Screenings
When you delete screenings through the web interface, the system now properly deletes:
- The encounter record
- All associated file records
- The ZIP file record

However, if you have old data that was deleted before this fix was implemented, you might have orphaned ZIP file records. Run the cleanup script to remove them.

### After Manual Database Operations
If you've manually deleted records from the database, you might have orphaned records. Use these scripts to clean them up.

### Regular Maintenance
These scripts can be run periodically as part of database maintenance to ensure data consistency.

## Safety Features

- **Dry Run Mode**: By default, all scripts run in dry-run mode and only report what would be deleted
- **Verbose Logging**: Use `--verbose` to see detailed information about each orphaned record
- **Transaction Safety**: All operations are wrapped in database transactions and will be rolled back on error
- **File Cleanup**: The comprehensive script also attempts to clean up orphaned files from disk

## Important Notes

- Always run in dry-run mode first to review what will be deleted
- The scripts search for files in recent date directories (last 7 days) when cleaning up disk files
- Make sure to have proper backups before running with `--execute`
- The scripts require the application environment to be properly configured

## Example Output

```
2025-10-23 14:22:27,724 - INFO - Starting orphaned record cleanup...
2025-10-23 14:22:27,724 - INFO - Mode: DRY RUN
2025-10-23 14:22:27,724 - INFO - Type: all

============================================================
CLEANUP SUMMARY
============================================================

Zip Files:
  Found: 0

Encounter Files:
  Found: 0

Pdf Files:
  Found: 0

Reports (DR + Glaucoma):
  Found: 0

============================================================
TOTAL Found: 0
Run with --execute to delete orphaned records
============================================================