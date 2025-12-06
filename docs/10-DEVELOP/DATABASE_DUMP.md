# Database Dump Feature

## Overview

The admin panel now includes a database dump feature that allows administrators to create a complete SQL dump of the entire database. This feature supports both PostgreSQL and SQLite databases.

## Access

The database dump feature is accessible at:
- **URL**: `/admin/database-dump`
- **Required Role**: `admin`

## Features

### Supported Database Types

1. **PostgreSQL** (Recommended for production)
   - Uses `pg_dump` command-line tool
   - Includes all tables, data, and structure
   - Options: `--no-owner`, `--no-privileges`, `--clean`, `--if-exists`

2. **SQLite** (Development environments)
   - Uses `sqlite3 .dump` command
   - Complete database structure and data
   - Compatible with SQLite restore

### Security Features

- **Role-based access**: Only users with `admin` role can access
- **CSRF protection**: All forms are protected with CSRF tokens
- **Audit logging**: All dump operations are logged
- **Temporary files**: Dump files are automatically cleaned up after download

### User Interface

- **Database information display**: Shows database type and size (PostgreSQL)
- **Progress feedback**: Loading states and error messages
- **Download prompt**: Automatic file download after dump creation
- **Responsive design**: Works on desktop and mobile devices

## Usage

### Web Interface

1. Navigate to `/admin/database-dump`
2. Review the database information displayed
3. Click "Create Database Dump" button
4. Wait for the dump to complete (may take several minutes)
5. File will automatically download as `database_dump_YYYYMMDD_HHMMSS.sql`

### API Endpoint

- **GET** `/admin/database-info` - Returns database information as JSON
  ```json
  {
    "database_type": "PostgreSQL",
    "database_size": "125 MB",
    "supports_dump": true
  }
  ```

## File Format

The dump is generated in standard SQL format:
- **PostgreSQL**: Plain SQL with PostgreSQL-specific syntax
- **SQLite**: SQLite-compatible SQL with `.dump` format

## Security Considerations

### Important Warnings

⚠️ **Sensitive Data**: Database dumps contain:
- Patient information and medical data
- User accounts and credentials (hashed)
- All grading and assessment data
- System configuration

### Best Practices

1. **Secure Storage**: Store dump files in encrypted, access-controlled locations
2. **Limited Retention**: Delete dump files when no longer needed
3. **Access Control**: Only authorized personnel should handle dumps
4. **Audit Trail**: All dump operations are logged with timestamps
5. **Network Security**: Use secure channels for file transfer

## Technical Details

### PostgreSQL Implementation

```bash
pg_dump \
  --no-owner \
  --no-privileges \
  --verbose \
  --clean \
  --if-exists \
  --format=plain \
  --dbname=$DATABASE_URL
```

### SQLite Implementation

```bash
sqlite3 /path/to/database.db ".dump"
```

### Error Handling

- **Timeout**: 5-minute limit for dump creation
- **Logging**: All errors logged to application logs
- **User Feedback**: Clear error messages displayed in UI
- **Cleanup**: Temporary files automatically removed

## Troubleshooting

### Common Issues

1. **Permission Denied**
   - Ensure `pg_dump` or `sqlite3` is in system PATH
   - Check database user permissions

2. **Timeout Errors**
   - Large databases may require more time
   - Consider database size before dumping

3. **Disk Space**
   - Ensure sufficient temporary space
   - Check available disk space before dumping

4. **Connection Issues**
   - Verify database connection string
   - Check database server availability

### Logs

Check application logs for detailed error information:
- Database connection errors
- Command execution failures
- File system permission issues

## Dependencies

### System Requirements

- **PostgreSQL**: `pg_dump` command-line tool
- **SQLite**: `sqlite3` command-line tool
- **Python**: Standard library (subprocess, tempfile, pathlib)

### Python Modules

- `flask` - Web framework
- `sqlalchemy` - Database ORM (for connection info)
- `urllib.parse` - URL parsing (PostgreSQL)
- `pathlib` - File path handling
- `tempfile` - Temporary file management

## Development Notes

### Testing

The feature includes comprehensive error handling and can be tested with:
- Different database types
- Invalid database URLs
- Permission scenarios
- Large database handling

### Extensibility

The architecture supports adding new database types:
1. Add detection logic in main function
2. Implement `_create_<db_type>_dump()` function
3. Update template with new type information

## Related Documentation

- [Admin Panel Overview](../ADMIN_PANEL.md)
- [Database Configuration](../DATABASE_SETUP.md)
- [Security Guidelines](../SECURITY.md)
- [Backup Procedures](../BACKUP_RESTORE.md)