# Grading Role Update Scripts

This directory contains scripts to update and manage grading roles in the database.

## update_admin_gradings.py

This script updates all existing admin gradings to ophthalmologist (consultant) for users who have both admin and ophthalmologist roles.

### Usage:
```bash
# Run with confirmation prompt
python scripts/update_admin_gradings.py

# Run without confirmation prompt
python scripts/update_admin_gradings.py --force
```

### What it does:
1. Identifies users who have both 'admin' and 'ophthalmologist' roles
2. Finds all gradings where these users have grader_role='admin'
3. Updates those gradings to have grader_role='consultant'

This ensures that when an admin user also has the ophthalmologist role, their gradings are recorded as "ophthalmologist" rather than "admin".

## backup_gradings.py

This script can create backups of the current grading state and restore from backups if needed.

### Usage:
```bash
# Create a backup
python scripts/backup_gradings.py --backup

# Create a backup with a specific filename
python scripts/backup_gradings.py --backup --backup-file my_backup.json

# Restore from a backup
python scripts/backup_gradings.py --restore my_backup.json

# Restore from a backup without confirmation
python scripts/backup_gradings.py --restore my_backup.json --force

# Show current grading statistics
python scripts/backup_gradings.py
```

## Important Notes:

1. **Always create a backup before running update_admin_gradings.py**
2. **Test the scripts in a development environment first**
3. **These scripts should only be run once, as a one-time migration**
4. **The update_admin_gradings.py script is designed to be idempotent - running it multiple times won't cause issues**