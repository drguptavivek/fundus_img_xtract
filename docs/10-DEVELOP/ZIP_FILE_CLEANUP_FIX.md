# ZIP File Cleanup Fix

## Issue

When screenings were deleted via `/screenings/delete/{id}`, the original ZIP files in `files/zips_upload_processed` were not being deleted from the file system, only the database records were removed.

## Root Cause

The `delete_encounter()` function in `screenings/routes.py` was missing the file system cleanup logic for ZIP files.

## Fix Applied

### Changes Made to `screenings/routes.py`

**Before:** Only deleted the database record
```python
# Also delete the ZIP file record to allow re-uploading the same ZIP
if zip_file:
    db.delete(zip_file)
```

**After:** Added file system cleanup
```python
# Also delete the ZIP file record and actual file to allow re-uploading the same ZIP
if zip_file:
    # Delete the actual ZIP file from disk
    try:
        from models import PROCESSED_DIR
        # ZIP files are stored in date subdirectories under PROCESSED_DIR
        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
        zip_file_path = PROCESSED_DIR / upload_date_str / zip_file.zip_filename

        if zip_file_path.exists():
            os.remove(zip_file_path)
            current_app.logger.info(f"Deleted ZIP file: {zip_file.zip_filename}")
        else:
            current_app.logger.warning(f"ZIP file not found for deletion: {zip_file_path}")
    except Exception as e:
        current_app.logger.error(f"Failed to delete ZIP file {zip_file.zip_filename}: {e}")

    # Delete the database record
    db.delete(zip_file)
```

### Key Fixes

1. **Correct Path Construction**:
   - Fixed to use `zip_file.zip_filename` instead of `zip_file.filename`
   - Added date subdirectory: `PROCESSED_DIR / upload_date_str / zip_file.zip_filename`

2. **Proper Error Handling**:
   - Added try-catch block with appropriate logging
   - Graceful handling if file doesn't exist

3. **Logging**:
   - Info level logging for successful deletions
   - Warning level for missing files
   - Error level for deletion failures

## File Structure

ZIP files are stored with the following structure:
```
files/zips_upload_processed/
├── 2025_11_11/
│   ├── 1712874_17-10-2025_0.05.07.821_PM.zip
│   ├── 17125503_29-08-2025_7.54.54.567_PM.zip
│   └── ...
└── 2025_11_12/
    └── (future uploads)
```

## Testing

The fix has been tested with:

1. **Path Resolution**: Verified correct path construction matches actual file locations
2. **File Deletion**: Confirmed `os.remove()` works on test files
3. **Error Handling**: Tested with non-existent files and directories
4. **Database Integration**: Confirmed `zip_file.zip_filename` and `zip_file.upload_date` fields contain correct values

## Impact

### Before Fix
- ZIP files remained on disk after screening deletion
- Accumulated orphaned files in `files/zips_upload_processed`
- Potential storage waste
- Manual cleanup required

### After Fix
- ZIP files automatically deleted when screening is deleted
- Clean file system with no orphaned ZIP files
- Automatic storage recovery
- No manual intervention needed

## Verification

To verify the fix is working:

1. **Monitor Logs**: Check for log messages like `"Deleted ZIP file: filename.zip"`
2. **Check File System**: Verify ZIP files are removed after screening deletion
3. **Storage Monitoring**: Monitor disk space recovery after bulk deletions

## Related Files

- **Modified**: `screenings/routes.py` - Added ZIP file cleanup logic
- **Referenced**: `models.py` - ZipFile model and PROCESSED_DIR constant
- **Directory**: `files/zips_upload_processed` - ZIP file storage location

## Rollback Plan

If issues occur, the fix can be rolled back by reverting the changes to `screenings/routes.py` and removing the file system cleanup logic while keeping the database record deletion.