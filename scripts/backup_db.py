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
from models import BASE_DIR, Session, Base

def get_expanded_database_url():
    """Get DATABASE_URL with proper environment variable expansion."""
    load_dotenv()
    
    # Get the raw DATABASE_URL
    database_url = os.getenv("DATABASE_URL")
    print(f"DEBUG: Raw DATABASE_URL = {database_url}")
    
    if not database_url:
        return None
    
    # Handle environment variable expansion for PostgreSQL URLs
    if "${" in database_url:
        print("DEBUG: Found ${} in DATABASE_URL, expanding variables...")
        # Expand environment variables manually
        database_url = database_url.replace("${POSTGRES_APP_USER}", os.getenv("POSTGRES_APP_USER", ""))
        database_url = database_url.replace("${POSTGRES_APP_PASSWORD}", os.getenv("POSTGRES_APP_PASSWORD", ""))
        database_url = database_url.replace("${POSTGRES_HOST}", os.getenv("POSTGRES_HOST", ""))
        database_url = database_url.replace("${POSTGRES_PORT}", os.getenv("POSTGRES_PORT", "5432"))
        database_url = database_url.replace("${POSTGRES_APP_DB}", os.getenv("POSTGRES_APP_DB", ""))
        print(f"DEBUG: Expanded DATABASE_URL = {database_url}")
    
    return database_url

# Import DATABASE_URL at module level for backward compatibility
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'image_manager.db'}")

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
    # Import DATABASE_URL for backward compatibility
    from models import DATABASE_URL
    
    # Use the expanded DATABASE_URL
    database_url = get_expanded_database_url()
    
    if not database_url:
        return None
    
    # Parse the DATABASE_URL to get database type and file path
    if database_url.startswith("sqlite"):
        # Extract the database file path from sqlite:///path/to/db
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            # If relative path, make it absolute from BASE_DIR
            db_path = BASE_DIR / db_path
        return {"type": "sqlite", "path": db_path}
    elif database_url.startswith("postgresql"):
        # For PostgreSQL, we need to extract connection details
        # Format: postgresql://user:pass@host:5432/db or postgresql+psycopg2://user:pass@host:5432/db
        import re
        # Pattern that matches both postgresql:// and postgresql+psycopg2://
        pattern = r"postgresql(\+psycopg2)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)"
        match = re.match(pattern, database_url)
        if match:
            return {
                "type": "postgresql",
                "user": match.group(2),
                "password": match.group(3),
                "host": match.group(4),
                "port": match.group(5),
                "database": match.group(6)
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
        # First try to use docker exec to run pg_dump in container
        docker_available = False
        try:
            # Check if docker is available and pgdb container is running
            result = subprocess.run(["docker", "ps", "--filter", "name=pgdb", "--format", "{{.Names}}"], 
                                  capture_output=True, text=True, check=True)
            if "pgdb" in result.stdout:
                docker_available = True
                print("Found PostgreSQL Docker container 'pgdb'")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Docker not available or pgdb container not found, trying local pg_dump...")
        
        if docker_available:
            # Use docker exec to run pg_dump inside the container
            print(f"Creating SQL dump for PostgreSQL database {db_info['database']} using Docker...")
            # Set environment variables for docker exec
            env = os.environ.copy()
            env["PGPASSWORD"] = db_info["password"]
            
            with open(sql_path, 'w') as f:
                subprocess.run([
                    "docker", "exec", "-e", "PGPASSWORD=" + db_info["password"], "pgdb",
                    "pg_dump",
                    "-U", db_info["user"],
                    "-d", db_info["database"],
                    "--verbose",
                    "--clean",
                    "--no-acl",
                    "--no-owner"
                ], stdout=f, check=True)
        else:
            # Try local pg_dump
            pg_dump_available = False
            try:
                subprocess.run(["pg_dump", "--version"], capture_output=True, check=True)
                pg_dump_available = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Local pg_dump not found, falling back to SQLAlchemy backup...")
            
            if pg_dump_available:
                # Set PGPASSWORD environment variable for pg_dump
                env = os.environ.copy()
                env["PGPASSWORD"] = db_info["password"]
                
                # Use pg_dump to create SQL dump
                print(f"Creating SQL dump for PostgreSQL database {db_info['database']} using local pg_dump...")
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
            else:
                # Fallback to SQLAlchemy backup
                print(f"Creating SQL dump for PostgreSQL database {db_info['database']} using SQLAlchemy...")
                
                # Create a direct database connection
                from sqlalchemy import create_engine, text
                
                # Construct the database URL
                db_url = f"postgresql://{db_info['user']}:{db_info['password']}@{db_info['host']}:{db_info['port']}/{db_info['database']}"
                engine = create_engine(db_url)
                
                with engine.connect() as conn:
                    # Get all table names
                    result = conn.execute(text("""
                        SELECT tablename 
                        FROM pg_tables 
                        WHERE schemaname = 'public'
                        ORDER BY tablename
                    """))
                    tables = [row[0] for row in result]
                    
                    # Write SQL dump
                    with open(sql_path, 'w') as f:
                        f.write(f"-- PostgreSQL database dump\n")
                        f.write(f"-- Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"-- Database: {db_info['database']}\n\n")
                        
                        # Add DROP statements
                        f.write("-- Drop statements\n")
                        for table in tables:
                            f.write(f"DROP TABLE IF EXISTS {table} CASCADE;\n")
                        f.write("\n")
                        
                        # Dump each table
                        for table in tables:
                            f.write(f"-- Data for table: {table}\n")
                            result = conn.execute(text(f"SELECT * FROM {table}"))
                            rows = result.fetchall()
                            
                            if rows:
                                # Get column names
                                columns = list(result.keys())
                                f.write(f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n")
                                
                                for i, row in enumerate(rows):
                                    values = []
                                    for value in row:
                                        if value is None:
                                            values.append("NULL")
                                        elif isinstance(value, str):
                                            # Escape single quotes in strings
                                            escaped_value = value.replace("'", "''")
                                            values.append(f"'{escaped_value}'")
                                        elif isinstance(value, bool):
                                            values.append("TRUE" if value else "FALSE")
                                        else:
                                            values.append(str(value))
                                    
                                    f.write(f"  ({', '.join(values)})")
                                    if i < len(rows) - 1:
                                        f.write(",\n")
                                    else:
                                        f.write(";\n")
                            else:
                                f.write(f"-- Table {table} is empty\n")
                            
                            f.write("\n")
        
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
        print(f"Current DATABASE_URL: {get_expanded_database_url()}")
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