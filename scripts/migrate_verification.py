"""
Add verification columns to patient_encounters: verified_status, verified_by, verified_at.

Usage:
  python scripts/migrate_verification.py           # apply changes
  python scripts/migrate_verification.py --dry-run # report only
"""

from __future__ import annotations
from pathlib import Path as _Path
import sys
import argparse
from dotenv import load_dotenv

load_dotenv()

_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models import engine  # noqa: E402


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()
    cols = [r[1] for r in rows]
    return column in cols


def migrate(dry_run: bool = False) -> None:
    with engine.begin() as conn:
        print("Inspecting patient_encounters for verification columns ...")
        adds = []
        if not column_exists(conn, 'patient_encounters', 'verified_status'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN verified_status TEXT")
        if not column_exists(conn, 'patient_encounters', 'verified_by'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN verified_by TEXT")
        if not column_exists(conn, 'patient_encounters', 'verified_at'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN verified_at DATETIME")
        if not adds:
            print("- All columns already present.")
        else:
            for sql in adds:
                print(f"- Will execute: {sql}")
                if not dry_run:
                    conn.exec_driver_sql(sql)
        # optional index on verified_status
        print("Ensuring index on verified_status ...")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_patient_encounters_verified_status ON patient_encounters (verified_status)")
    print("Done." if not dry_run else "Dry run complete (no changes applied).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add verification fields to patient_encounters")
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == '__main__':
    main()

