#!/usr/bin/env python3
"""
Script to create timestamped database and app backups on the host.

USAGE:
    python3 scripts/backup_db.py

DESCRIPTION:
This script creates a complete backup of the PostgreSQL database by:
1. Running pg_dump inside the Docker Compose db service
2. Writing the dump to ~/backups on the host
3. Verifying gzip integrity and md5 checksums for both archives

It also creates a tar.gz of the app code (excluding ./files and ./logs).

Backup files:
- backup_YYYYMMDD_HHMMSS_db.tar.gz
- backup_YYYYMMDD_HHMMSS_app.tar.gz
- backup_YYYYMMDD_HHMMSS_checksums.md5
"""

import hashlib
import os
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

def compute_md5(file_path):
    """Compute md5 hash for a file."""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            md5.update(chunk)
    return md5.hexdigest()

def verify_md5(file_path, expected_digest):
    """Verify md5 hash matches expected value."""
    actual = compute_md5(file_path)
    if actual != expected_digest:
        raise ValueError(f"MD5 mismatch for {file_path.name}")
    print(f"MD5 OK: {file_path.name} {actual}")

def verify_gzip(file_path):
    """Verify gzip integrity for a .gz file."""
    print(f"GZIP CHECK: {file_path.name}")
    subprocess.run(["gzip", "-t", str(file_path)], check=True)
    print(f"GZIP OK: {file_path.name}")

def create_postgresql_backup(backup_dir, timestamp):
    """Create tar.gz backup for PostgreSQL database."""
    sql_filename = f"backup_{timestamp}_db.sql"
    tar_filename = f"backup_{timestamp}_db.tar.gz"
    
    sql_path = backup_dir / sql_filename
    tar_path = backup_dir / tar_filename
    
    try:
        print("Creating SQL dump using Docker Compose db service...")
        with open(sql_path, 'w') as f:
            subprocess.run([
                "docker", "compose", "exec", "-T", "db",
                "bash", "-lc",
                'pg_dump -U "$POSTGRES_APP_USER" -d "$POSTGRES_APP_DB"'
            ], stdout=f, check=True)
        
        print(f"SQL dump created: {sql_filename}")
        print(f"Creating compressed archive: {tar_filename}...")
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(sql_path, arcname=sql_filename)
        os.remove(sql_path)
        verify_gzip(tar_path)
        
        print(f"Backup completed successfully: {tar_filename}")
        return tar_path
        
    except subprocess.CalledProcessError as e:
        print(f"Error creating PostgreSQL dump: {e}")
        if sql_path.exists():
            os.remove(sql_path)
        if tar_path.exists():
            os.remove(tar_path)
        return None
    except Exception as e:
        print(f"Error during backup: {e}")
        if sql_path.exists():
            os.remove(sql_path)
        if tar_path.exists():
            os.remove(tar_path)
        return None

def create_app_backup(backup_dir, timestamp):
    """Create tar.gz backup of the app code excluding ./files and ./logs."""
    tar_filename = f"backup_{timestamp}_app.tar.gz"
    tar_path = backup_dir / tar_filename

    repo_root = Path(__file__).resolve().parents[1]
    repo_name = repo_root.name
    exclude_dirs = {
        Path(repo_name) / ".git",
        Path(repo_name) / ".venv",
        Path(repo_name) / "backups",
        Path(repo_name) / "files",
        Path(repo_name) / "logs",
        Path(repo_name) / "tmp",
        Path(repo_name) / "__pycache__",
    }

    def tar_filter(tarinfo):
        path = Path(tarinfo.name)
        for excluded in exclude_dirs:
            if path == excluded or excluded in path.parents:
                return None
        return tarinfo

    try:
        print(f"Creating app backup archive: {tar_filename}...")
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(repo_root, arcname=repo_root.name, filter=tar_filter)
        verify_gzip(tar_path)
        print(f"App backup completed successfully: {tar_filename}")
        return tar_path
    except Exception as e:
        print(f"Error during app backup: {e}")
        if tar_path.exists():
            os.remove(tar_path)
        return None

def main():
    """Main backup function."""
    print("=" * 60)
    print("Database Backup Script")
    print("=" * 60)
    
    # Ensure backups directory exists in home
    backup_dir = Path.home() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nBackup directory: {backup_dir}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = create_postgresql_backup(backup_dir, timestamp)
    app_backup_file = create_app_backup(backup_dir, timestamp)
    checksums_path = backup_dir / f"backup_{timestamp}_checksums.md5"
    checksums = {}
    if backup_file:
        checksums[backup_file.name] = compute_md5(backup_file)
    if app_backup_file:
        checksums[app_backup_file.name] = compute_md5(app_backup_file)
    if checksums and backup_file and app_backup_file:
        for name, digest in checksums.items():
            file_path = backup_dir / name
            print(f"MD5: {name} {digest}")
            verify_md5(file_path, digest)
        with open(checksums_path, "w") as f:
            for name, digest in sorted(checksums.items()):
                f.write(f"{digest}  {name}\n")
    
    if backup_file and app_backup_file:
        # Get file size for reporting
        file_size = backup_file.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        print("=" * 60)
        print(f"SUCCESS: Backup created!")
        print(f"File: {backup_file.name}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Location: {backup_file}")
        if app_backup_file:
            app_file_size = app_backup_file.stat().st_size
            app_file_size_mb = app_file_size / (1024 * 1024)
            print(f"App File: {app_backup_file.name}")
            print(f"App Size: {app_file_size_mb:.2f} MB")
            print(f"App Location: {app_backup_file}")
        if checksums:
            print(f"Checksums: {checksums_path}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("ERROR: Backup failed!")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
