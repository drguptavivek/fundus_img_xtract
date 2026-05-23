# Database Backup and Restore Scripts

This directory contains scripts for backing up and restoring the Fundus Image Manager database.

## Scripts

### list_backups.py
Lists all available database backups in the backups directory.

**Usage:**
```bash
uv run scripts/list_backups.py
```

**What it does:**
1. Scans the `backups/` directory for backup files
2. Displays backup files with creation date and file size
3. Shows helpful commands for backup and restore operations

**Output:**
- Numbered list of backup files
- File size in human-readable format
- Creation timestamp
- Example commands for backup/restore

### backup_db.py
Creates timestamped tar-gzipped archives for the database and app code.

**Usage:**
```bash
uv run scripts/backup_db.py
```

**What it does:**
1. Creates a complete SQL dump from the Docker Compose database service
2. Compresses the SQL dump into a timestamped tar.gz archive
3. Creates a timestamped app-code tar.gz archive
4. Excludes local runtime data from the app archive, including `backups/`, `files/`, `logs/`, `tmp/`, `.venv/`, `.git/`, `__pycache__/`, and `REMIDIO_Samples/`
5. Stores the archives and checksum file in `~/backups`

**Output:**
- Database archive named: `backup_YYYYMMDD_HHMMSS_db.tar.gz`
- App archive named: `backup_YYYYMMDD_HHMMSS_app.tar.gz`
- Checksum file named: `backup_YYYYMMDD_HHMMSS_checksums.md5`
- Located in: `~/backups`

**Supported databases:**
- PostgreSQL through Docker Compose

**Example output:**
```
============================================================
Database Backup Script
============================================================
Database type: sqlite

Analyzing database...

Table Record Counts:
--------------------------------------------------
users                                   2 records
hospitals                               2 records
patients                               1,234 records
grades                                567 records
--------------------------------------------------
TOTAL                               1,805 records
--------------------------------------------------

Backup directory: /path/to/project/backups
Creating SQL dump for SQLite database...
SQL dump created: db_backup_20251103_103007.sql
Creating compressed archive: db_backup_20251103_103007.tar.gz...
Backup completed successfully: db_backup_20251103_103007.tar.gz
============================================================
SUCCESS: Backup created!
File: db_backup_20251103_103007.tar.gz
Size: 0.12 MB
Location: /path/to/project/backups/db_backup_20251103_103007.tar.gz
============================================================
```

### restore_db.py
Restores the database from a backup created by `backup_db.py`.

**Usage:**
```bash
uv run scripts/restore_db.py <backup_file> [--force]
```

**Examples:**
```bash
# Restore with confirmation prompt
uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz

# Restore without confirmation (useful for scripts)
uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz --force
```

**What it does:**
1. Extracts SQL file from the tar.gz archive
2. Creates a backup of the current database (for SQLite)
3. Modifies SQL to drop existing tables before creating new ones
4. Restores the database from the SQL dump
5. Cleans up temporary files

**⚠️ WARNING:** This will completely replace the current database with the backup. All current data will be permanently lost.

**Note:** The restore script automatically creates a backup of the current database before restoring (e.g., `image_manager.db.backup`).

## Environment Configuration

The scripts use the same `DATABASE_URL` environment variable as the main application:

- **SQLite:** `sqlite:///image_manager.db` (default)
- **PostgreSQL:** `postgresql+psycopg2://user:pass@host:5432/db`

## Prerequisites

### For SQLite
- `sqlite3` command-line tool (usually pre-installed)

### For PostgreSQL
- `pg_dump` for creating backups
- `psql` for restoring backups
- PostgreSQL client tools installed

## Examples

### Listing available backups
```bash
# List all available backups
uv run scripts/list_backups.py

# Output:
# ================================================================================
# Database Backups
# ================================================================================
# Found 1 backup(s) in: /path/to/project/backups
# --------------------------------------------------------------------------------
# #   Filename                            Size       Modified
# --------------------------------------------------------------------------------
# 1   db_backup_20251103_103007.tar.gz    6.1 KB     2025-11-03 10:30:07
# --------------------------------------------------------------------------------
#
# Commands:
#   Create backup:     uv run scripts/backup_db.py
#   Restore backup:    uv run scripts/restore_db.py <filename>
#   Example restore:   uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz
```

### Creating a backup
```bash
# Create a backup of the current database
uv run scripts/backup_db.py

# Output:
# ============================================================
# Database Backup Script
# ============================================================
# Database type: sqlite
# Backup directory: /path/to/project/backups
# Creating SQL dump for SQLite database...
# SQL dump created: db_backup_20251103_103007.sql
# Creating compressed archive: db_backup_20251103_103007.tar.gz...
# Backup completed successfully: db_backup_20251103_103007.tar.gz
# ============================================================
# SUCCESS: Backup created!
# File: db_backup_20251103_103007.tar.gz
# Size: 0.01 MB
# Location: /path/to/project/backups/db_backup_20251103_103007.tar.gz
# ============================================================
```

### Restoring from backup
```bash
# Restore from a specific backup file
uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz

# You'll be prompted for confirmation:
# ============================================================
# WARNING: This will completely replace current database!
# All current data will be permanently lost.
# ============================================================
# Type 'RESTORE DATABASE' to confirm this action: RESTORE DATABASE
```

## Best Practices

1. **Regular Backups:** Schedule regular backups, especially before major changes
2. **Verify Backups:** Periodically test restore procedures to ensure backups are valid
3. **Storage:** Consider moving backups to off-site storage for disaster recovery
4. **Retention:** Implement a backup retention policy to manage disk space
5. **Security:** Ensure backup files are stored securely as they contain sensitive data

## Automation

You can automate backups using cron (Linux/macOS) or Task Scheduler (Windows):

### Example cron entry (daily at 2 AM):
```bash
0 2 * * * cd /path/to/fundus_img_xtract && uv run scripts/backup_db.py
```

## Troubleshooting

### Common Issues

1. **"sqlite3: command not found"**
   - Install SQLite tools: `brew install sqlite` (macOS) or `apt-get install sqlite3` (Ubuntu)

2. **"pg_dump: command not found"**
   - Install PostgreSQL client tools: `brew install postgresql` (macOS) or `apt-get install postgresql-client` (Ubuntu)

3. **Permission denied**
   - Ensure the script has execute permissions and the backups directory is writable

4. **Database connection errors**
   - Verify DATABASE_URL in your .env file is correct
   - Check database server is running and accessible

### Getting Help

If you encounter issues:
1. Check the error messages carefully
2. Verify your database connection settings
3. Ensure required command-line tools are installed
4. Check file permissions on the backups directory
