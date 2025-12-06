# Cleanup Duplicate Images Script

This document provides instructions for using the `cleanup_duplicate_images.py` script to remove duplicate DirectImageUpload records and their associated data from the database.

## Overview

The script identifies duplicate images based on their `file_hash` and removes all duplicates while keeping the oldest record (first uploaded). For each duplicate removed, it also cleans up all associated data including:
- DirectImageVerify records
- GradingTask records
- Grade records
- Consensus records
- TaskTracker records
- ImageGrading records

Optionally, it can also delete the actual image files from disk.

## Prerequisites

- Python environment with uv package manager
- Access to the database
- Appropriate permissions to modify the database

## Usage

### 1. Dry Run (Recommended First)

To see what duplicates exist without making any changes:

```bash
uv run scripts/cleanup_duplicate_images.py
```

This will show:
- Number of duplicate groups found
- Total duplicate records to remove
- Counts of associated data that will be removed
- Details of which records will be kept and which will be removed

### 2. Execute Cleanup

To actually perform the cleanup after reviewing the dry run:

```bash
uv run scripts/cleanup_duplicate_images.py --execute
```

The script will:
1. Show the same analysis as the dry run
2. Ask for confirmation before proceeding
3. Remove all duplicates and their associated data
4. Commit the changes to the database

### 3. Execute Cleanup with File Deletion

To also delete the actual image files from disk:

```bash
uv run scripts/cleanup_duplicate_images.py --execute --cleanup-files
```

⚠️ **Warning**: This will permanently delete the duplicate image files from your filesystem.

## What Gets Removed

Based on the dry run output, the script will remove:
- **135 duplicate DirectImageUpload records**
- **135 DirectImageVerify records**
- **135 GradingTask records**
- **0 Grade records**
- **0 Consensus records**
- **0 TaskTracker records**
- **0 ImageGrading records**

The script keeps the oldest record in each duplicate group (based on creation date).

## Safety Features

1. **Dry Run Mode**: Default mode shows what would be changed without making any modifications
2. **Confirmation Prompt**: Requires explicit confirmation before executing the cleanup
3. **Transactional**: All changes are committed together or rolled back on error
4. **Orderly Deletion**: Removes data in the correct order to respect foreign key constraints

## Rollback

If you need to rollback the changes after execution:
1. Restore from a database backup taken before running the script
2. If no backup is available, you'll need to manually re-import the deleted images

## Troubleshooting

### Permission Errors
Ensure you have:
- Database write permissions
- File system permissions (if using --cleanup-files)

### Database Connection Issues
Check that:
- The database is accessible
- Environment variables are properly set
- The application can connect to the database

### Script Errors
If the script encounters an error:
1. Check the error message for details
2. Ensure all dependencies are installed
3. Verify the database schema matches expectations

## Best Practices

1. **Always run a dry run first** to understand what will be deleted
2. **Take a database backup** before executing the cleanup
3. **Run during maintenance window** to minimize user impact
4. **Monitor the application** after cleanup to ensure everything works correctly

## Script Details

The script:
1. Groups duplicates by `file_hash`
2. Keeps the oldest record in each group
3. Removes all other records in the group
4. Cleans up associated data in the correct order
5. Optionally removes files from disk
6. Provides detailed logging throughout the process