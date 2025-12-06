# Disk Usage Management

## Overview

The admin disk usage page provides tools for managing disk space by cleaning up unnecessary files. This includes deleting duplicate ZIP files and removing old processed ZIP files that are no longer needed.

## Access

Navigate to `/admin/disk-usage` to access the disk usage analysis page. This page is restricted to users with admin role.

## Features

### 1. Disk Usage Analysis

The page displays a tree view of directories under:
- `files/` - Contains all uploaded and processed files
- `logs/` - Contains application logs

For each directory, it shows:
- Directory name
- Total size (human-readable format)
- Number of subdirectories
- Usage percentage (visual progress bar)
- Last modified date
- Actions (expand/collapse)

### 2. Delete Duplicate Files

**Purpose**: Removes duplicate ZIP files that were detected during upload.

**How duplicates are created**:
- When a ZIP file is uploaded, the system calculates an MD5 hash
- If a ZIP file with the same MD5 hash already exists in the database, the new file is considered a duplicate
- Duplicates are moved to `dupmd5_YYYY-MM-DD` directories in the files root

**Deletion process**:
1. Click the "Delete All Duplicates" button (appears only when duplicate directories exist)
2. Confirm the action in the dialog
3. All files in all `dupmd5_*` directories are deleted
4. Empty directories are removed
5. A success message shows how many files were deleted and space freed

**Safety considerations**:
- Original files are never deleted - only duplicates
- The first-seen file with each MD5 hash is kept in the system
- All extracted images and PDFs from duplicates remain in the system

### 3. Delete Old Processed ZIP Files

**Purpose**: Removes ZIP files that have already been processed and are older than 1 month.

**How processed ZIP files are stored**:
- After successful processing, ZIP files are moved to `files/zips_upload_processed/`
- They're organized by date in subdirectories (format: `YYYY_MM_DD`)
- The extracted images and PDFs are stored separately and remain in the system

**Deletion criteria**:
- Only ZIP files in directories older than 30 days are deleted
- The system checks the directory name (which contains the date) to determine age
- Only the original ZIP files are deleted, not the extracted content

**Deletion process**:
1. Click the "Delete Old ZIP Files (>1 month)" button (appears only when old ZIP files exist)
2. Confirm the action in the dialog
3. All ZIP files in date directories older than 30 days are deleted
4. Empty directories are removed
5. A success message shows how many files were deleted, from which directories, and space freed

**Safety considerations**:
- Only processed ZIP files are deleted - extracted images and PDFs remain intact
- The button only appears when eligible files exist
- Confirmation dialog prevents accidental deletion
- Detailed logging of all deletions

## File Locations

### Duplicate Files
- Location: `files/dupmd5_YYYY-MM-DD/`
- Created when: A ZIP file with the same MD5 hash is uploaded again
- Contains: Duplicate ZIP files only

### Processed ZIP Files
- Location: `files/zips_upload_processed/YYYY_MM_DD/`
- Created when: ZIP files are successfully processed
- Contains: Original ZIP files after processing
- Deleted when: Older than 30 days via admin interface

### Extracted Content (Never deleted by these tools)
- Images: `files/zip_upload_images/YYYY_MM_DD/`
- PDFs: `files/zip_upload_pdfs/YYYY_MM_DD/`
- DR Reports: `files/zip_dr_pdfs/YYYY_MM_DD/`
- Glaucoma Reports: `files/zip_glaucoma_pdfs/YYYY_MM_DD/`

## Logging

All deletion actions are logged:
- Which files were deleted
- How much space was freed
- Which directories were cleaned
- Any errors encountered

Logs are written to the application log and can be viewed via the admin log viewer.

## Implementation Details

### Backend Routes
- `/admin/disk-usage` - Main disk usage page (GET)
- `/admin/disk-usage/delete-duplicates` - Delete duplicates (POST)
- `/admin/disk-usage/delete-old-zips` - Delete old processed ZIPs (POST)

### Security
- All routes require admin role
- CSRF protection on all forms
- Confirmation dialogs for destructive actions

### Error Handling
- Graceful handling of permission errors
- Skips files that cannot be accessed
- Continues processing other files if one fails
- User-friendly error messages

## Best Practices

1. **Regular Cleanup**: Run the cleanup operations regularly to prevent disk space issues
2. **Monitor Logs**: Check the logs after cleanup operations to verify what was deleted
3. **Backup Important Data**: Ensure you have backups before performing large cleanup operations
4. **Check Disk Usage**: Use the analysis view to identify which directories are using the most space

## Troubleshooting

### Button Not Visible
- **Delete Duplicates**: No `dupmd5_*` directories exist in the files folder
- **Delete Old ZIPs**: No processed ZIP files older than 30 days exist

### Files Not Deleted
- Check if files are locked by another process
- Verify file permissions
- Check the application logs for error messages

### Unexpected Behavior
- Check the logs for detailed error information
- Verify the directory structure matches expectations
- Ensure sufficient disk space for operations