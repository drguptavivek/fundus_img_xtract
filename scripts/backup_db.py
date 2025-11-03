#!/usr/bin/env python3
"""
Script to create a timestamped tar-gzipped SQL dump of the entire database.

USAGE:
    uv run scripts/backup_db.py

DESCRIPTION:
This script creates a complete backup of the database by:
1. Creating a SQL dump of the entire database
2. Compressing it with gzip
3. Creating a tar archive with timestamp
4. Storing it in the backups directory

The backup file will be named: db_backup_YYYYMMDD_HHMMSS.tar.gz
"""

import sys
import os
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

# Add project root directory to path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from models import DATABASE_URL, BASE_DIR, Session, Base

def get_table_record_counts():
    """Get record counts for all tables in the database."""
    db = Session()
    try:
        counts = {}
        
        # Get all table names from the metadata
        from sqlalchemy import inspect, text
        inspector = inspect(db.bind)
        table_names = inspector.get_table_names()
        
        for table_name in table_names:
            try:
                # Use raw SQL to get count for each table
                sql = text(f"SELECT COUNT(*) FROM {table_name}")
                result = db.execute(sql)
                count = result.scalar()
                if count > 0:  # Only show tables with records
                    counts[table_name] = count
            except Exception as e:
                # Skip tables that can't be counted (e.g., system tables)
                continue
        
        return counts
    except Exception as e:
        print(f"Warning: Could not get table counts: {e}")
        return {}
    finally:
        db.close()

def print_table_counts(counts):
    """Print table record counts in a formatted way."""
    if not counts:
        return
    
    print("\nTable Record Counts:")
    print("-" * 50)
    # Sort by table name
    for table_name in sorted(counts.keys()):
        count = counts[table_name]
        print(f"{table_name:<30} {count:>10,} records")
    print("-" * 50)
    total_records = sum(counts.values())
    print(f"{'TOTAL':<30} {total_records:>10,} records")
    print("-" * 50)

def get_database_info():
    """Extract database information from DATABASE_URL."""
    load_dotenv()
    
    # Parse the DATABASE_URL to get database type and file path
    if DATABASE_URL.startswith("sqlite"):
        # Extract the database file path from sqlite:///path/to/db
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

def create_sqlite_backup(db_path, backup_dir):
    """Create backup for SQLite database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_filename = f"db_backup_{timestamp}.sql"
    tar_filename = f"db_backup_{timestamp}.tar.gz"
    
    sql_path = backup_dir / sql_filename
    tar_path = backup_dir / tar_filename
    
    try:
        # Use sqlite3 command to dump the database
        print(f"Creating SQL dump for SQLite database at {db_path}...")
        with open(sql_path, 'w') as f:
            subprocess.run([
                "sqlite3", str(db_path), ".dump"
            ], stdout=f, check=True)
        
        print(f"SQL dump created: {sql_filename}")
        
        # Create tar.gz archive
        print(f"Creating compressed archive: {tar_filename}...")
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(sql_path, arcname=sql_filename)
        
        # Remove the intermediate SQL file
        os.remove(sql_path)
        
        print(f"Backup completed successfully: {tar_filename}")
        return tar_path
        
    except subprocess.CalledProcessError as e:
        print(f"Error creating SQLite dump: {e}")
        # Clean up on error
        if sql_path.exists():
            os.remove(sql_path)
        if tar_path.exists():
            os.remove(tar_path)
        return None
    except Exception as e:
        print(f"Error during backup: {e}")
        # Clean up on error
        if sql_path.exists():
            os.remove(sql_path)
        if tar_path.exists():
            os.remove(tar_path)
        return None

def create_postgresql_backup(db_info, backup_dir):
    """Create backup for PostgreSQL database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sql_filename = f"db_backup_{timestamp}.sql"
    tar_filename = f"db_backup_{timestamp}.tar.gz"
    
    sql_path = backup_dir / sql_filename
    tar_path = backup_dir / tar_filename
    
    try:
        # Set PGPASSWORD environment variable for pg_dump
        env = os.environ.copy()
        env["PGPASSWORD"] = db_info["password"]
        
        # Use pg_dump to create the SQL dump
        print(f"Creating SQL dump for PostgreSQL database {db_info['database']}...")
        with open(sql_path, 'w') as f:
            subprocess.run([
                "pg_dump",
                "-h", db_info["host"],
                "-p", str(db_info["port"]),
                "-U", db_info["user"],
                "-d", db_info["database"],
                "--no-password",
                "--verbose",
                "--clean",
                "--no-acl",
                "--no-owner"
            ], stdout=f, env=env, check=True)
        
        print(f"SQL dump created: {sql_filename}")
        
        # Create tar.gz archive
        print(f"Creating compressed archive: {tar_filename}...")
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(sql_path, arcname=sql_filename)
        
        # Remove the intermediate SQL file
        os.remove(sql_path)
        
        print(f"Backup completed successfully: {tar_filename}")
        return tar_path
        
    except subprocess.CalledProcessError as e:
        print(f"Error creating PostgreSQL dump: {e}")
        # Clean up on error
        if sql_path.exists():
            os.remove(sql_path)
        if tar_path.exists():
            os.remove(tar_path)
        return None
    except Exception as e:
        print(f"Error during backup: {e}")
        # Clean up on error
        if sql_path.exists():
            os.remove(sql_path)
        if tar_path.exists():
            os.remove(tar_path)
        return None

def main():
    """Main backup function."""
    print("=" * 60)
    print("Database Backup Script")
    print("=" * 60)
    
    # Get database information
    db_info = get_database_info()
    if not db_info:
        print("ERROR: Could not parse DATABASE_URL")
        print(f"Current DATABASE_URL: {DATABASE_URL}")
        sys.exit(1)
    
    print(f"Database type: {db_info['type']}")
    
    # Get and display table record counts before backup
    print("\nAnalyzing database...")
    table_counts = get_table_record_counts()
    print_table_counts(table_counts)
    
    # Ensure backups directory exists
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    print(f"\nBackup directory: {backup_dir}")
    
    # Create backup based on database type
    if db_info["type"] == "sqlite":
        if not os.path.exists(db_info["path"]):
            print(f"ERROR: SQLite database file not found: {db_info['path']}")
            sys.exit(1)
        
        backup_file = create_sqlite_backup(db_info["path"], backup_dir)
        
    elif db_info["type"] == "postgresql":
        backup_file = create_postgresql_backup(db_info, backup_dir)
        
    else:
        print(f"ERROR: Unsupported database type: {db_info['type']}")
        sys.exit(1)
    
    if backup_file:
        # Get file size for reporting
        file_size = backup_file.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        print("=" * 60)
        print(f"SUCCESS: Backup created!")
        print(f"File: {backup_file.name}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Location: {backup_file}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("ERROR: Backup failed!")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()