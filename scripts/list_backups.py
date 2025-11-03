#!/usr/bin/env python3
"""
Script to list all available database backups.

USAGE:
    uv run scripts/list_backups.py

DESCRIPTION:
This script lists all database backup files in the backups directory
with their creation date and file size.
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BASE_DIR

def format_size(size_bytes):
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

def main():
    """List all backup files."""
    print("=" * 80)
    print("Database Backups")
    print("=" * 80)
    
    backup_dir = BASE_DIR / "backups"
    
    if not backup_dir.exists():
        print(f"Backup directory does not exist: {backup_dir}")
        sys.exit(1)
    
    # Find all backup files
    backup_files = []
    for file_path in backup_dir.glob("db_backup_*.tar.gz"):
        stat = file_path.stat()
        backup_files.append({
            "path": file_path,
            "name": file_path.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime)
        })
    
    # Sort by modification time (newest first)
    backup_files.sort(key=lambda x: x["modified"], reverse=True)
    
    if not backup_files:
        print("No backup files found.")
        print(f"Backup directory: {backup_dir}")
        print("\nTo create a backup, run:")
        print("  uv run scripts/backup_db.py")
        return
    
    # Display backup files
    print(f"Found {len(backup_files)} backup(s) in: {backup_dir}")
    print("-" * 80)
    print(f"{'#':<3} {'Filename':<35} {'Size':<10} {'Modified':<20}")
    print("-" * 80)
    
    for i, backup in enumerate(backup_files, 1):
        print(f"{i:<3} {backup['name']:<35} {format_size(backup['size']):<10} {backup['modified'].strftime('%Y-%m-%d %H:%M:%S'):<20}")
    
    print("-" * 80)
    print("\nCommands:")
    print("  Create backup:     uv run scripts/backup_db.py")
    print("  Restore backup:    uv run scripts/restore_db.py <filename>")
    print("  Example restore:   uv run scripts/restore_db.py backups/db_backup_20251103_103007.tar.gz")

if __name__ == "__main__":
    main()