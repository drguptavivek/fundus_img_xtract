# scripts/migrate_uuid.py
import argparse
import os
import time
from pathlib import Path
from typing import Tuple

# Optional: load .env if python-dotenv is available
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def _counts_sqlalchemy(conn) -> Tuple[int, int, int]:
    total = conn.exec_driver_sql("SELECT COUNT(*) FROM encounter_files").scalar() or 0
    missing = conn.exec_driver_sql(
        "SELECT COUNT(*) FROM encounter_files WHERE uuid IS NULL OR uuid = ''"
    ).scalar() or 0
    distinct = conn.exec_driver_sql(
        "SELECT COUNT(DISTINCT uuid) FROM encounter_files WHERE uuid IS NOT NULL AND uuid <> ''"
    ).scalar() or 0
    return int(total), int(missing), int(distinct)


def _indexes_sqlalchemy(conn):
    try:
        rows = conn.exec_driver_sql("PRAGMA index_list('encounter_files')").fetchall()
        return [(r[1], bool(r[2])) for r in rows]
    except Exception:
        return []


def _ensure_uuid_for_table_sqlalchemy(conn, table: str, *, batch_size: int = 1000, progress_every: int = 10) -> None:
    start = time.monotonic()
    print(f"[uuid] Inspecting schema for {table} ...")
    # 1) Add column if missing
    cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info('{table}')").fetchall()]
    if 'uuid' not in cols:
        print(f"[uuid] Adding column 'uuid' to {table} ...")
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
    else:
        print(f"[uuid] Column 'uuid' already exists on {table}.")

    # 2) Backfill in batches
    missing_total = conn.exec_driver_sql(
        f"SELECT COUNT(*) FROM {table} WHERE uuid IS NULL OR uuid = ''"
    ).scalar() or 0
    missing_total = int(missing_total)
    if missing_total == 0:
        print(f"[uuid] No rows require backfill for {table}.")
    else:
        print(f"[uuid] Backfilling UUIDs for {missing_total} rows on {table} (batch_size={batch_size}) ...")
    processed = 0
    batch_num = 0
    while True:
        # Perform batch update
        conn.exec_driver_sql(
            f"""
            WITH to_update AS (
                SELECT id FROM {table}
                WHERE uuid IS NULL OR uuid = ''
                LIMIT {int(batch_size)}
            )
            UPDATE {table}
            SET uuid = lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-' || '4' ||
                              substr(hex(randomblob(2)), 2) || '-' ||
                              substr('AB89', abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)), 2) || '-' ||
                              hex(randomblob(6)))
            WHERE id IN (SELECT id FROM to_update);
            """
        )
        # Get rows actually changed in this connection
        rows_updated = int(conn.exec_driver_sql("SELECT changes()").scalar() or 0)
        if rows_updated <= 0:
            break
        processed += rows_updated
        batch_num += 1
        if missing_total and (batch_num % max(1, progress_every) == 0 or processed >= missing_total):
            elapsed = time.monotonic() - start
            pct = (processed / missing_total * 100) if missing_total else 100.0
            print(f"[uuid] {table} backfill: {processed}/{missing_total} ({pct:.1f}%) in {elapsed:.1f}s ...")

    # 3) Unique index
    print(f"[uuid] Ensuring unique index on {table}(uuid) ...")
    conn.exec_driver_sql(
        f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table}_uuid ON {table} (uuid)"
    )
    elapsed_total = time.monotonic() - start
    print(f"[uuid] {table} migration finished in {elapsed_total:.1f}s.")


def _ensure_uuid_sqlalchemy(conn, *, batch_size: int = 1000, progress_every: int = 10) -> None:
    _ensure_uuid_for_table_sqlalchemy(conn, 'encounter_files', batch_size=batch_size, progress_every=progress_every)


def run(check_only: bool = False, show_indexes: bool = False, *, batch_size: int = 1000, progress_every: int = 10) -> None:
    # Try to reuse the app's SQLAlchemy engine first
    engine = None
    try:
        from models import engine as app_engine  # type: ignore
        engine = app_engine
    except Exception:
        engine = None

    if engine is not None:
        print("Using SQLAlchemy engine from models.py ...")
        # Inspect schema first to avoid querying a missing column
        with engine.begin() as conn:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info('encounter_files')").fetchall()]
            uuid_exists = 'uuid' in cols
            if uuid_exists:
                total, missing, distinct = _counts_sqlalchemy(conn)
                print(f"Before: total={total}, missing_uuid={missing}, distinct_uuid={distinct}")
                if show_indexes:
                    for name, is_unique in _indexes_sqlalchemy(conn):
                        print(f"  - {name} (unique={is_unique})")
            else:
                # Can't compute missing/distinct without the column
                total = conn.exec_driver_sql("SELECT COUNT(*) FROM encounter_files").scalar() or 0
                print(f"Before: total={int(total)}, uuid_column=missing")

        if check_only:
            print("Check-only mode: no changes applied.")
            return

        print("Running migration/backfill for EncounterFile.uuid ...")
        # Ensure column + backfill
        with engine.begin() as conn:
            # Encounter files
            _ensure_uuid_for_table_sqlalchemy(conn, 'encounter_files', batch_size=batch_size, progress_every=progress_every)
            # Reports
            _ensure_uuid_for_table_sqlalchemy(conn, 'diabetic_retinopathy_reports', batch_size=batch_size, progress_every=progress_every)
            _ensure_uuid_for_table_sqlalchemy(conn, 'glaucoma_reports', batch_size=batch_size, progress_every=progress_every)

        with engine.begin() as conn:
            total, missing, distinct = _counts_sqlalchemy(conn)
            print(f"After:  total={total}, missing_uuid={missing}, distinct_uuid={distinct}")
            if show_indexes:
                for name, is_unique in _indexes_sqlalchemy(conn):
                    print(f"  - {name} (unique={is_unique})")
        return

    # Fallback: direct sqlite3 (no SQLAlchemy import)
    import sqlite3
    base_dir = Path(__file__).resolve().parent
    db_url = os.getenv("DATABASE_URL", f"sqlite:///{base_dir / 'zip_processing.db'}")
    if not db_url.startswith("sqlite"):
        raise RuntimeError("Fallback path only supports SQLite DATABASE_URL.")
    db_path = db_url.split("sqlite:///")[-1]

    print(f"Using sqlite3 fallback at {db_path} ...")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        def counts() -> Tuple[int, int, int]:
            cur.execute("SELECT COUNT(*) AS c FROM encounter_files")
            total = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM encounter_files WHERE uuid IS NULL OR uuid = ''")
            missing = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT uuid) FROM encounter_files WHERE uuid IS NOT NULL AND uuid <> ''")
            distinct = cur.fetchone()[0]
            return int(total or 0), int(missing or 0), int(distinct or 0)

        # Check if uuid column exists before selecting it
        cur.execute("PRAGMA table_info('encounter_files')")
        cols = [row[1] for row in cur.fetchall()]
        uuid_exists = 'uuid' in cols
        if uuid_exists:
            total, missing, distinct = counts()
            print(f"Before: total={total}, missing_uuid={missing}, distinct_uuid={distinct}")
        else:
            cur.execute("SELECT COUNT(*) FROM encounter_files")
            total = int(cur.fetchone()[0] or 0)
            print(f"Before: total={total}, uuid_column=missing")

        if check_only:
            print("Check-only mode: no changes applied.")
            return

        # Ensure column exists
        if not uuid_exists:
            cur.execute("ALTER TABLE encounter_files ADD COLUMN uuid TEXT")
            conn.commit()

        print(f"[uuid] Backfilling UUIDs (batch_size={batch_size}) ...")
        start = time.monotonic()
        cur.execute("SELECT COUNT(*) FROM encounter_files WHERE uuid IS NULL OR uuid = ''")
        missing_total = int(cur.fetchone()[0] or 0)
        processed = 0
        batch_num = 0
        while True:
            cur.execute(
                f"""
                WITH to_update AS (
                    SELECT id FROM encounter_files
                    WHERE uuid IS NULL OR uuid = ''
                    LIMIT {int(batch_size)}
                )
                UPDATE encounter_files
                SET uuid = lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-' || '4' ||
                                  substr(hex(randomblob(2)), 2) || '-' ||
                                  substr('AB89', abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)), 2) || '-' ||
                                  hex(randomblob(6)))
                WHERE id IN (SELECT id FROM to_update);
                """
            )
            # Use total_changes delta for reliable row count
            cur.execute("SELECT changes()")
            rows_updated = int(cur.fetchone()[0] or 0)
            if rows_updated <= 0:
                break
            processed += rows_updated
            batch_num += 1
            conn.commit()
            if missing_total and (batch_num % max(1, progress_every) == 0 or processed >= missing_total):
                elapsed = time.monotonic() - start
                pct = (processed / missing_total * 100) if missing_total else 100.0
                print(f"[uuid] Backfill progress: {processed}/{missing_total} ({pct:.1f}%) in {elapsed:.1f}s ...")

        # Unique index
        print("[uuid] Ensuring unique index on encounter_files(uuid) ...")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_encounter_files_uuid ON encounter_files (uuid)"
        )
        conn.commit()

        total, missing, distinct = counts()
        print(f"After:  total={total}, missing_uuid={missing}, distinct_uuid={distinct}")

        # Also ensure report tables via sqlite3
        def ensure_table_sqlite(table: str):
            print(f"[uuid] Ensuring {table}.uuid ...")
            cur.execute(f"PRAGMA table_info('{table}')")
            cols = [row[1] for row in cur.fetchall()]
            if 'uuid' not in cols:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN uuid TEXT")
                conn.commit()
            # Backfill
            start2 = time.monotonic()
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE uuid IS NULL OR uuid = ''")
            missing2 = int(cur.fetchone()[0] or 0)
            processed2 = 0
            while True:
                cur.execute(
                    f"""
                    WITH to_update AS (
                        SELECT id FROM {table}
                        WHERE uuid IS NULL OR uuid = ''
                        LIMIT {int(batch_size)}
                    )
                    UPDATE {table}
                    SET uuid = lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-' || '4' ||
                                      substr(hex(randomblob(2)), 2) || '-' ||
                                      substr('AB89', abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)), 2) || '-' ||
                                      hex(randomblob(6)))
                    WHERE id IN (SELECT id FROM to_update);
                    """
                )
                cur.execute("SELECT changes()")
                rc = int(cur.fetchone()[0] or 0)
                if rc <= 0:
                    break
                processed2 += rc
                conn.commit()
                if missing2:
                    elapsed2 = time.monotonic() - start2
                    pct2 = processed2 / missing2 * 100
                    print(f"[uuid] {table} backfill: {processed2}/{missing2} ({pct2:.1f}%) in {elapsed2:.1f}s ...")
            cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table}_uuid ON {table} (uuid)")
            conn.commit()

        ensure_table_sqlite('diabetic_retinopathy_reports')
        ensure_table_sqlite('glaucoma_reports')


def main():
    parser = argparse.ArgumentParser(
        description="Ensure and backfill UUIDs for encounter_files, with counts before/after."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only show counts; do not apply migration/backfill.",
    )
    parser.add_argument(
        "--show-indexes",
        action="store_true",
        help="Print index list (only when using SQLAlchemy/sqlite).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=1000,
        help="Rows to update per batch (default: 1000)"
    )
    parser.add_argument(
        "--progress-every", type=int, default=10,
        help="Print progress every N batches (default: 10)"
    )
    args = parser.parse_args()

    run(
        check_only=args.check_only,
        show_indexes=args.show_indexes,
        batch_size=max(1, args.batch_size),
        progress_every=max(1, args.progress_every),
    )


if __name__ == "__main__":
    main()
