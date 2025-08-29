"""
Add graded_for column to image_gradings and create a unique index over
  (encounter_file_id, grader_user_id, grader_role, graded_for).
Backfill existing rows to 'glaucoma'.

Usage:
  python scripts/migrate_image_grading_graded_for.py
  python scripts/migrate_image_grading_graded_for.py --dry-run
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
    return any(r[1] == column for r in rows)


def index_exists(conn, table: str, index_name: str) -> bool:
    try:
        rows = conn.exec_driver_sql(f"PRAGMA index_list('{table}')").fetchall()
    except Exception:
        return False
    return any(r[1] == index_name for r in rows)


def migrate(dry_run: bool = False) -> None:
    with engine.begin() as conn:
        print("Inspecting image_gradings for graded_for column ...")
        if not column_exists(conn, 'image_gradings', 'graded_for'):
            print("- Will add graded_for (TEXT)")
            if not dry_run:
                conn.exec_driver_sql("ALTER TABLE image_gradings ADD COLUMN graded_for TEXT")
        else:
            print("- graded_for already exists")

        print("Backfilling graded_for to 'glaucoma' where NULL ...")
        if not dry_run:
            conn.exec_driver_sql("UPDATE image_gradings SET graded_for = 'glaucoma' WHERE graded_for IS NULL OR graded_for = ''")

        idx_name = 'uq_image_grading_image_user_role_for'
        if not index_exists(conn, 'image_gradings', idx_name):
            print(f"- Will create unique index {idx_name}")
            if not dry_run:
                conn.exec_driver_sql(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON image_gradings (encounter_file_id, grader_user_id, grader_role, graded_for)"
                )
        else:
            print(f"- Index {idx_name} already exists")
    print("Done." if not dry_run else "Dry run complete (no changes applied).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Add graded_for to image_gradings")
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == '__main__':
    main()

