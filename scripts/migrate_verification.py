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
        print("Inspecting patient_encounters for glaucoma/DR verification columns ...")
        adds = []
        # Glaucoma
        if not column_exists(conn, 'patient_encounters', 'glaucoma_verified_status'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN glaucoma_verified_status TEXT")
        if not column_exists(conn, 'patient_encounters', 'glaucoma_verified_by'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN glaucoma_verified_by TEXT")
        if not column_exists(conn, 'patient_encounters', 'glaucoma_verified_at'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN glaucoma_verified_at DATETIME")
        # DR
        if not column_exists(conn, 'patient_encounters', 'dr_verified_status'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN dr_verified_status TEXT")
        if not column_exists(conn, 'patient_encounters', 'dr_verified_by'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN dr_verified_by TEXT")
        if not column_exists(conn, 'patient_encounters', 'dr_verified_at'):
            adds.append("ALTER TABLE patient_encounters ADD COLUMN dr_verified_at DATETIME")
        if not adds:
            print("- All columns already present.")
        else:
            for sql in adds:
                print(f"- Will execute: {sql}")
                if not dry_run:
                    conn.exec_driver_sql(sql)
        # optional indexes
        print("Ensuring index on glaucoma_verified_status ...")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_patient_encounters_glaucoma_verified_status ON patient_encounters (glaucoma_verified_status)")
        print("Ensuring index on dr_verified_status ...")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_patient_encounters_dr_verified_status ON patient_encounters (dr_verified_status)")

        # Backfill from old columns if they exist
        print("Backfilling glaucoma_* from legacy verified_* if present ...")
        if column_exists(conn, 'patient_encounters', 'verified_status'):
            if not dry_run:
                conn.exec_driver_sql(
                    "UPDATE patient_encounters SET glaucoma_verified_status = COALESCE(glaucoma_verified_status, verified_status)"
                )
        if column_exists(conn, 'patient_encounters', 'verified_by'):
            if not dry_run:
                conn.exec_driver_sql(
                    "UPDATE patient_encounters SET glaucoma_verified_by = COALESCE(glaucoma_verified_by, verified_by)"
                )
        if column_exists(conn, 'patient_encounters', 'verified_at'):
            if not dry_run:
                conn.exec_driver_sql(
                    "UPDATE patient_encounters SET glaucoma_verified_at = COALESCE(glaucoma_verified_at, verified_at)"
                )
    print("Done." if not dry_run else "Dry run complete (no changes applied).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add verification fields to patient_encounters")
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
