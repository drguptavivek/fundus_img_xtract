"""
Add `eye_side` column to encounter_files and create an index.

Usage:
  # Normal run (adds column if missing, ensures index)
  python scripts/migrate_eye_side.py

  # Dry run (show what would change)
  python scripts/migrate_eye_side.py --dry-run

Notes:
  - Uses the SQLAlchemy engine configured in models.py
  - SQLite compatible; uses PRAGMA to inspect schema
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path as _Path
from typing import List

from dotenv import load_dotenv

load_dotenv()

# Ensure project root on path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models import engine  # noqa: E402


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()
    cols = [r[1] for r in rows]
    return column in cols


def index_exists(conn, table: str, index_name: str) -> bool:
    try:
        rows = conn.exec_driver_sql(f"PRAGMA index_list('{table}')").fetchall()
    except Exception:
        return False
    return any(r[1] == index_name for r in rows)


def migrate(dry_run: bool = False) -> None:
    print("Inspecting schema for encounter_files.eye_side ...")
    with engine.begin() as conn:
        has_col = column_exists(conn, "encounter_files", "eye_side")
        if has_col:
            print("- Column 'eye_side' already exists on encounter_files.")
        else:
            print("- Column 'eye_side' is missing and will be added (TEXT, NULL, indexed).")
            if not dry_run:
                conn.exec_driver_sql("ALTER TABLE encounter_files ADD COLUMN eye_side TEXT")

        # Ensure index (non-unique)
        idx_name = "ix_encounter_files_eye_side"
        has_idx = index_exists(conn, "encounter_files", idx_name)
        if has_idx:
            print(f"- Index '{idx_name}' already exists on encounter_files.")
        else:
            print(f"- Index '{idx_name}' will be created.")
            if not dry_run:
                conn.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {idx_name} ON encounter_files (eye_side)"
                )

    print("Migration complete." if not dry_run else "Dry run complete (no changes applied).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add eye_side to encounter_files and index it")
    ap.add_argument("--dry-run", action="store_true", help="Do not apply changes; only report")
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

