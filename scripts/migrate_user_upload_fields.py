"""
Add file_upload_quota and file_upload_count columns to the users table.
Also ensures the user_lab_units association table exists.

Usage:
  python scripts/migrate_user_upload_fields.py
  python scripts/migrate_user_upload_fields.py --dry-run
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path as _Path
from dotenv import load_dotenv

load_dotenv()

_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models import engine, Base  # noqa: E402

def column_exists(conn, table: str, column: str) -> bool:
    try:
        rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()
        return any(r[1] == column for r in rows)
    except Exception:
        return False

def migrate(dry_run: bool = False) -> None:
    # This call ensures that all tables defined in models.py, including the
    # new 'user_lab_units' association table, are created if they don't exist.
    print("Ensuring all tables from models are created...")
    if not dry_run:
        Base.metadata.create_all(engine)
        print("- Tables created or already exist.")
    else:
        print("- (Skipped in dry-run mode)")

    with engine.begin() as conn:
        print("\nInspecting 'users' table for quota columns...")
        ops: list[str] = []
        
        if not column_exists(conn, 'users', 'file_upload_quota'):
            ops.append("ALTER TABLE users ADD COLUMN file_upload_quota INTEGER DEFAULT 0 NOT NULL")
        else:
            print("- Column 'file_upload_quota' already exists.")

        if not column_exists(conn, 'users', 'file_upload_count'):
            ops.append("ALTER TABLE users ADD COLUMN file_upload_count INTEGER DEFAULT 0 NOT NULL")
        else:
            print("- Column 'file_upload_count' already exists.")

        if not ops:
            print("- All required columns are already present in the 'users' table.")
        else:
            for sql in ops:
                print(f"- Will execute: {sql}")
                if not dry_run:
                    conn.exec_driver_sql(sql)
    
    print("\nMigration complete." if not dry_run else "\nDry run complete (no changes were applied).")

def main() -> None:
    ap = argparse.ArgumentParser(description="Add upload quota and lab unit association fields to the users table.")
    ap.add_argument('--dry-run', action='store_true', help="Show what would change without applying it.")
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)

if __name__ == '__main__':
    main()
