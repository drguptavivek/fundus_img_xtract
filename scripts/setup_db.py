# scripts/setup_db.py


import argparse
from dotenv import load_dotenv
import sys
from pathlib import Path as _Path
from datetime import datetime
import sqlite3


# Ensure project root is importable when running this script directly
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Ensure env is loaded (DATABASE_URL, etc.)
load_dotenv()

from models import Base, engine  # noqa: E402


def _maybe_backup_sqlite(engine, backup_dir=_ROOT / "backups" / "sqlite"):
    """
    If the SQLAlchemy engine points to a file-based SQLite DB, create a
    timestamped backup using the sqlite3 backup API. Returns Path or None.
    """
    try:
        # Works for "sqlite" or "sqlite+pysqlite"
        if engine.url.get_backend_name() != "sqlite":
            print("[sqlite-backup] Non-SQLite engine detected; skipping.")
            return None

        db_path_str = engine.url.database
        if not db_path_str or db_path_str == ":memory:":
            print("[sqlite-backup] In-memory SQLite; skipping.")
            return None

        db_path = _Path(db_path_str)
        if not db_path.is_absolute():
            db_path = (_ROOT / db_path).resolve()

        if not db_path.exists():
            print(f"[sqlite-backup] File not found at {db_path}; skipping.")
            return None

        backup_dir = _Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = db_path.suffix or ".db"
        backup_path = backup_dir / f"{db_path.stem}_{ts}{suffix}"

        print(f"[sqlite-backup] Creating backup: {backup_path}")
        with sqlite3.connect(str(db_path)) as src, sqlite3.connect(str(backup_path)) as dst:
            src.backup(dst)  # consistent snapshot
        print("[sqlite-backup] Backup complete.")
        return backup_path
    except Exception as e:
        print(f"[sqlite-backup] Backup failed: {e}")
        return None

def create_tables() -> None:
    print("Creating database tables (if missing)...", flush=True)
    Base.metadata.create_all(engine)
    print("Tables are ready.", flush=True)

def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database and optionally backfill UUIDs.")

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="When used with --migrate-uuids, show counts only and do not apply changes",
    )
   
    parser.add_argument(
        "--setup-core-disease-gradings",
        action="store_true",
        help="Set up standard gradings for core diseases (Glaucoma, DR, AMD)",
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for UUID backfill (default: 1000)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Print progress every N batches (default: 10)",
    )
    args = parser.parse_args()

    create_tables()
   
           
    if args.setup_core_disease_gradings:
        try:
            from setup_core_disease_gradings import setup_core_disease_gradings as setup_gradings
            setup_gradings(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import setup_core_disease_gradings: {e}")

def setup_core_disease_gradings(dry_run: bool = False) -> None:
    """Set up standard gradings for core diseases."""
    print("Preparing to set up standard gradings for core diseases...")
    try:
        from setup_core_disease_gradings import setup_core_disease_gradings as setup_gradings
        if not dry_run:
            setup_gradings()
        else:
            print("Dry run: Would set up standard gradings for core diseases")
    except Exception as e:
        print(f"Failed to import setup_core_disease_gradings: {e}")


if __name__ == "__main__":
    _maybe_backup_sqlite(engine)
    main()
