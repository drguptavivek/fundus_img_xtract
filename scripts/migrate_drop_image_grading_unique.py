"""
Drop unique index/constraint for image_gradings to allow multiple gradings
by the same grader for intra-rater agreement. Create a non-unique composite
index to keep lookups efficient.

Usage:
  python scripts/migrate_drop_image_grading_unique.py
  python scripts/migrate_drop_image_grading_unique.py --dry-run
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


def index_list(conn, table: str):
    try:
        return conn.exec_driver_sql(f"PRAGMA index_list('{table}')").fetchall()
    except Exception:
        return []


def migrate(dry_run: bool = False) -> None:
    with engine.begin() as conn:
        print("Checking indexes on image_gradings ...")
        idxs = index_list(conn, 'image_gradings')
        names = [r[1] for r in idxs]
        # Drop previously created unique index if present
        uniq_name = 'uq_image_grading_image_user_role_for'
        if uniq_name in names:
            print(f"- Will drop unique index {uniq_name}")
            if not dry_run:
                conn.exec_driver_sql(f"DROP INDEX IF EXISTS {uniq_name}")
        else:
            print(f"- Unique index {uniq_name} not found (ok)")

        # Ensure non-unique composite index exists
        ix_name = 'ix_image_gradings_image_user_role_for'
        if ix_name not in names:
            print(f"- Will create non-unique index {ix_name}")
            if not dry_run:
                conn.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {ix_name} ON image_gradings (encounter_file_id, grader_user_id, grader_role, graded_for)"
                )
        else:
            print(f"- Non-unique index {ix_name} already exists")

    print("Done." if not dry_run else "Dry run complete (no changes applied).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Drop unique index on image_gradings and add non-unique index")
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == '__main__':
    main()

