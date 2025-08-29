"""
Backfill PatientEncounters.capture_date_dt from capture_date strings.

Usage:
  python scripts/migrate_capture_date_dt.py            # run migration
  python scripts/migrate_capture_date_dt.py --dry-run  # just report counts

Notes:
  - Works with the SQLAlchemy engine configured in models.py
  - Adds the column if missing (SQLite: ALTER TABLE)
  - Accepts multiple date formats: YYYY-MM-DD, YYYY/MM/DD, DD-MM-YYYY, DD/MM/YYY, MM/DD/YYYY, MM-DD-YYYY
"""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Iterable

from dotenv import load_dotenv
import sys
from pathlib import Path as _Path

load_dotenv()

# Ensure project root is importable when running this script directly
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models import engine  # noqa: E402


DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%m-%d-%Y",
)


def parse_date_str(s: str | None) -> str | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(s, fmt).date()
            return d.isoformat()
        except Exception:
            continue
    return None


def ensure_column(conn) -> None:
    cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info('patient_encounters')").fetchall()]
    if "capture_date_dt" not in cols:
        conn.exec_driver_sql("ALTER TABLE patient_encounters ADD COLUMN capture_date_dt DATE")


def rows_to_update(conn) -> Iterable[tuple[int, str | None]]:
    rs = conn.exec_driver_sql(
        "SELECT id, capture_date FROM patient_encounters WHERE capture_date_dt IS NULL"
    ).fetchall()
    for r in rs:
        yield int(r[0]), (r[1] if len(r) > 1 else None)


def migrate(dry_run: bool = False) -> None:
    with engine.begin() as conn:
        ensure_column(conn)
        all_rows = list(rows_to_update(conn))
        total = len(all_rows)
        if total == 0:
            print("No rows require backfill. capture_date_dt is up-to-date.")
            return
        print(f"Found {total} rows to backfill.")

        updated = 0
        skipped = 0
        for rid, cap in all_rows:
            iso = parse_date_str(cap)
            if iso is None:
                skipped += 1
                continue
            updated += 1
            if not dry_run:
                conn.exec_driver_sql(
                    "UPDATE patient_encounters SET capture_date_dt = :iso WHERE id = :rid",
                    {"iso": iso, "rid": rid},
                )

        print(f"Updated rows: {updated}")
        print(f"Skipped rows (unparsed): {skipped}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill capture_date_dt for PatientEncounters")
    ap.add_argument("--dry-run", action="store_true", help="Do not write changes, only report")
    args = ap.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
