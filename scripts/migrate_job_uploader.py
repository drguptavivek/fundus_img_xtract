"""
Add uploader metadata columns to jobs and job_items tables:
 - jobs: uploader_user_id (INT), uploader_username (TEXT), uploader_ip (TEXT)
 - job_items: uploader_user_id (INT), uploader_username (TEXT), uploader_ip (TEXT)

Usage:
  python scripts/migrate_job_uploader.py
  python scripts/migrate_job_uploader.py --dry-run
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

from models import engine  # noqa: E402


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()
    return any(r[1] == column for r in rows)


def migrate(dry_run: bool = False) -> None:
    with engine.begin() as conn:
        print("Inspecting jobs/job_items for uploader columns ...")
        ops: list[str] = []
        # jobs
        if not column_exists(conn, 'jobs', 'uploader_user_id'):
            ops.append("ALTER TABLE jobs ADD COLUMN uploader_user_id INTEGER")
        if not column_exists(conn, 'jobs', 'uploader_username'):
            ops.append("ALTER TABLE jobs ADD COLUMN uploader_username TEXT")
        if not column_exists(conn, 'jobs', 'uploader_ip'):
            ops.append("ALTER TABLE jobs ADD COLUMN uploader_ip TEXT")
        # job_items
        if not column_exists(conn, 'job_items', 'uploader_user_id'):
            ops.append("ALTER TABLE job_items ADD COLUMN uploader_user_id INTEGER")
        if not column_exists(conn, 'job_items', 'uploader_username'):
            ops.append("ALTER TABLE job_items ADD COLUMN uploader_username TEXT")
        if not column_exists(conn, 'job_items', 'uploader_ip'):
            ops.append("ALTER TABLE job_items ADD COLUMN uploader_ip TEXT")

        if not ops:
            print("- All columns already present.")
        else:
            for sql in ops:
                print(f"- Will execute: {sql}")
                if not dry_run:
                    conn.exec_driver_sql(sql)
    print("Done." if not dry_run else "Dry run complete (no changes applied).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add uploader columns to jobs and job_items")
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == '__main__':
    main()

