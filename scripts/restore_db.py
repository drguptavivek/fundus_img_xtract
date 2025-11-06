#!/usr/bin/env python3
"""
Script to restore database from a timestamped tar-gzipped SQL backup.

USAGE:
    uv run scripts/restore_db.py <backup_file>

DESCRIPTION:
This script restores a database from a backup created by backup_db.py:
1. Extracts SQL file from tar.gz archive
2. Creates a backup of current database (for SQLite)
3. Restores database from SQL dump
4. Cleans up temporary files

WARNING: This will completely replace the current database with backup.
All current data will be permanently lost.
"""

import sys
import os
import subprocess
import tarfile
from pathlib import Path

# Add project root directory to path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import DATABASE_URL, BASE_DIR

def get_database_info():
    """Extract database information from DATABASE_URL."""
    # Environment is already loaded by utils.env_loader imported in models
    
    # Parse DATABASE_URL to get database type and file path
    if DATABASE_URL.startswith("sqlite"):
        # Extract database file path from sqlite:///path/to/db
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            # If relative path, make it absolute from BASE_DIR
            db_path = BASE_DIR / db_path
        return {"type": "sqlite", "path": db_path}
    elif DATABASE_URL.startswith("postgresql"):
        # For PostgreSQL, we need to extract connection details
        # Format: postgresql+psycopg2://user:pass@host:5432/db
        import re
        pattern = r"postgresql\+psycopg2://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
        match = re.match(pattern, DATABASE_URL)
        if match:
            return {
                "type": "postgresql",
                "user": match.group(1),
                "password": match.group(2),
                "host": match.group(3),
                "port": match.group(4),
                "database": match.group(5)
            }
    return None

def extract_sql_from_backup(backup_path, temp_dir):
    """Extract SQL file from tar.gz backup."""
    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            # Find the SQL file in the archive
            sql_file = None
            for member in tar.getmembers():
                if member.name.endswith('.sql'):
                    sql_file = member
                    break
            
            if not sql_file:
                print("ERROR: No SQL file found in backup archive")
                return None
            
            # Extract the SQL file
            tar.extract(sql_file, temp_dir)
            sql_path = temp_dir / sql_file.name
            
            print(f"Extracted SQL file: {sql_file.name}")
            return sql_path
            
    except Exception as e:
        print(f"ERROR: Failed to extract backup: {e}")
        return None

def restore_sqlite_database(sql_path, db_path):
    """Restore SQLite database from SQL dump."""
    try:
        # Create a backup of current database before restoring
        if os.path.exists(db_path):
            backup_db_path = db_path.with_suffix('.db.backup')
            print(f"Creating backup of current database: {backup_db_path}")
            import shutil
            shutil.copy2(db_path, backup_db_path)
        
        # For SQLite restore, we need to drop existing tables first
        # Read the SQL file and modify it to drop tables before creating
        with open(sql_path, 'r') as f:
            sql_content = f.read()
        
        # Add DROP TABLE statements before CREATE TABLE statements
        import re
        # This regex matches CREATE TABLE statements and adds DROP TABLE IF EXISTS before them
        # It extracts the table name and includes it in the DROP statement
        modified_sql = re.sub(
            r'CREATE TABLE\s+(\w+)',
            r'DROP TABLE IF EXISTS \1;\nCREATE TABLE \1',
            sql_content
        )
        
        # Write modified SQL to temporary file
        temp_sql_path = sql_path.with_suffix('.modified.sql')
        with open(temp_sql_path, 'w') as f:
            f.write(modified_sql)
        
        # Restore from modified SQL dump
        print(f"Restoring SQLite database from {temp_sql_path}...")
        with open(temp_sql_path, 'r') as f:
            subprocess.run([
                "sqlite3", str(db_path)
            ], stdin=f, check=True)
        
        # Clean up temporary file
        os.remove(temp_sql_path)
        
        print("SQLite database restored successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to restore SQLite database: {e}")
        return False
    except Exception as e:
        print(f"ERROR: During SQLite restore: {e}")
        return False

def restore_postgresql_database(sql_path, db_info):
    """Restore PostgreSQL database from SQL dump."""
    try:
        # Set PGPASSWORD environment variable for psql
        env = os.environ.copy()
        env["PGPASSWORD"] = db_info["password"]
        
        # Restore from SQL dump
        print(f"Restoring PostgreSQL database {db_info['database']} from {sql_path}...")
        with open(sql_path, 'r') as f:
            subprocess.run([
                "psql",
                "-h", db_info["host"],
                "-p", str(db_info["port"]),
                "-U", db_info["user"],
                "-d", db_info["database"],
                "--no-password",
                "--quiet",
                "--set", "ON_ERROR_STOP=on"
            ], stdin=f, env=env, check=True)
        
        print("PostgreSQL database restored successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to restore PostgreSQL database: {e}")
        return False
    except Exception as e:
        print(f"ERROR: During PostgreSQL restore: {e}")
        return False

def main():
    """Main restore function."""
    if len(sys.argv) < 2:
        print("USAGE: uv run scripts/restore_db.py <backup_file> [--force]")
        print("Example: uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz")
        print("        uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz --force")
        sys.exit(1)
    
    backup_file = sys.argv[1]
    
    # Convert to absolute path if relative
    if not os.path.isabs(backup_file):
        backup_file = BASE_DIR / backup_file
    
    backup_path = Path(backup_file)
    
    if not backup_path.exists():
        print(f"ERROR: Backup file not found: {backup_path}")
        sys.exit(1)
    
    if not backup_path.name.endswith('.tar.gz'):
        print("ERROR: Backup file must be a .tar.gz file")
        sys.exit(1)
    
    print("=" * 60)
    print("Database Restore Script")
    print("=" * 60)
    print(f"Backup file: {backup_path}")
    
    # Get database information
    db_info = get_database_info()
    if not db_info:
        print("ERROR: Could not parse DATABASE_URL")
        print(f"Current DATABASE_URL: {DATABASE_URL}")
        sys.exit(1)
    
    print(f"Database type: {db_info['type']}")
    
    # Create temporary directory for extraction
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Extract SQL file from backup
        sql_path = extract_sql_from_backup(backup_path, temp_path)
        if not sql_path:
            sys.exit(1)
        
        # Confirm restoration (skip if --force flag is provided)
        if len(sys.argv) > 2 and sys.argv[2] == "--force":
            print("Force flag detected - skipping confirmation.")
        else:
            print("=" * 60)
            print("WARNING: This will completely replace the current database!")
            print("All current data will be permanently lost.")
            print("=" * 60)
            
            confirmation = input("Type 'RESTORE DATABASE' to confirm this action: ")
            if confirmation != "RESTORE DATABASE":
                print("Operation cancelled. No data was restored.")
                sys.exit(0)
        
        # Restore based on database type
        success = False
        if db_info["type"] == "sqlite":
            success = restore_sqlite_database(sql_path, db_info["path"])
        elif db_info["type"] == "postgresql":
            success = restore_postgresql_database(sql_path, db_info)
        else:
            print(f"ERROR: Unsupported database type: {db_info['type']}")
            sys.exit(1)
        
        if success:
            print("=" * 60)
            print("SUCCESS: Database restored successfully!")
            print("=" * 60)
        else:
            print("=" * 60)
            print("ERROR: Database restore failed!")
            print("=" * 60)
            sys.exit(1)

if __name__ == "__main__":
    main()