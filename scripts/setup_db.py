# scripts/setup_db.py
"""
Standalone database setup utility.

Usage examples (PowerShell):
  # Create tables only (fast)
  python scripts/setup_db.py

  # Create tables + backfill UUIDs (EncounterFile + Reports)
  python scripts/setup_db.py --migrate-uuids

  # Check-only UUID migration (no changes, just counts/indexes)
  python scripts/setup_db.py --migrate-uuids --check-only

Options:
  --batch-size N        Rows to update per batch (UUID backfill)
  --progress-every N    Print progress every N batches
"""

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


def migrate_uuids(check_only: bool, batch_size: int, progress_every: int) -> None:
    print("Preparing UUID backfill for EncounterFile + Reports ...", flush=True)
    try:
        # Reuse migration helper which handles encounter_files and reports
        from migrate_uuid import run  # noqa: E402
    except Exception as e:  # pragma: no cover
        print(f"Failed to import migrate_uuid.py: {e}")
        return

    run(
        check_only=check_only,
        show_indexes=True,
        batch_size=max(1, batch_size),
        progress_every=max(1, progress_every),
    )


def migrate_eye_side(dry_run: bool) -> None:
    print("Preparing migration for encounter_files.eye_side ...", flush=True)
    try:
        from migrate_eye_side import migrate  # type: ignore
    except Exception as e:  # pragma: no cover
        print(f"Failed to import migrate_eye_side.py: {e}")
        return
    migrate(dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database and optionally backfill UUIDs.")
    parser.add_argument(
        "--migrate-uuids",
        action="store_true",
        help="Also ensure/backfill UUIDs for encounter_files and report tables",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="When used with --migrate-uuids, show counts only and do not apply changes",
    )
    parser.add_argument(
        "--migrate-eye-side",
        action="store_true",
        help="Add eye_side column to encounter_files and index it",
    )
    parser.add_argument(
        "--migrate-verification",
        action="store_true",
        help="Add verification columns to patient_encounters",
    )
    parser.add_argument(
        "--migrate-image-grading-for",
        action="store_true",
        help="Add graded_for to image_gradings and unique index",
    )
    parser.add_argument(
        "--drop-image-grading-unique",
        action="store_true",
        help="Drop unique constraint/index on image_gradings and create a non-unique index",
    )
    parser.add_argument(
        "--migrate-job-uploader",
        action="store_true",
        help="Add uploader metadata columns to jobs and job_items",
    )
    parser.add_argument(
        "--migrate-direct-uploads",
        action="store_true",
        help="Create tables for direct image uploads feature",
    )
    parser.add_argument(
        "--migrate-direct-uploads-edited-image",
        action="store_true",
        help="Add edited_image_path column to direct_image_uploads table",
    )
    parser.add_argument(
        "--migrate-image-grading-direct-upload",
        action="store_true",
        help="Add direct_image_upload_id column to image_gradings table",
    )
    parser.add_argument(
        "--migrate-image-grading-nullable-columns",
        action="store_true",
        help="Modify image_gradings table to allow NULL values for encounter_file_id and direct_image_upload_id",
    )
    parser.add_argument(
        "--migrate-anonymization-verifications",
        action="store_true",
        help="Create tables for direct image anonymization verifications feature",
    )
    parser.add_argument(
        "--migrate-disease-gradings",
        action="store_true",
        help="Create tables for disease gradings feature",
    )
    parser.add_argument(
        "--migrate-missing-roles",
        action="store_true",
        help="Add any missing roles to the database",
    )
    parser.add_argument(
        "--migrate-encounter-files-lab-unit",
        action="store_true",
        help="Add lab_unit_id column to encounter_files table",
    )
    parser.add_argument(
        "--migrate-user-disease-specializations",
        action="store_true",
        help="Create user_disease_specializations table",
    )
    parser.add_argument(
        "--migrate-core-diseases",
        action="store_true",
        help="Ensure core diseases (Glaucoma, DR, AMD) exist with correct IDs",
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
    if args.migrate_uuids:
        migrate_uuids(args.check_only, args.batch_size, args.progress_every)
    if args.migrate_eye_side:
        migrate_eye_side(dry_run=args.check_only)
    if args.migrate_verification:
        try:
            from migrate_verification import migrate as migrate_verif
            migrate_verif(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_verification: {e}")
    if args.migrate_image_grading_for:
        try:
            from migrate_image_grading_graded_for import migrate as mig_gr_for
            mig_gr_for(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_image_grading_graded_for: {e}")
    if args.drop_image_grading_unique:
        try:
            from migrate_drop_image_grading_unique import migrate as drop_unique
            drop_unique(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_drop_image_grading_unique: {e}")
    if args.migrate_job_uploader:
        try:
            from migrate_job_uploader import migrate as mig_job_upl
            mig_job_upl(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_job_uploader: {e}")
    if args.migrate_direct_uploads:
        try:
            from migrate_direct_uploads import migrate as mig_direct_upl
            mig_direct_upl()
        except Exception as e:
            print(f"Failed to import migrate_direct_uploads: {e}")
    if args.migrate_direct_uploads_edited_image:
        try:
            from migrate_direct_uploads_edited_image import migrate as mig_direct_upl_edited
            mig_direct_upl_edited(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_direct_uploads_edited_image: {e}")
    if args.migrate_anonymization_verifications:
        try:
            from migrate_anonymization_verifications import migrate as mig_anon_verif
            mig_anon_verif(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_anonymization_verifications: {e}")
    if args.migrate_disease_gradings:
        try:
            from migrate_disease_grading import main as mig_disease_grading
            mig_disease_grading()
        except Exception as e:
            print(f"Failed to import migrate_disease_grading: {e}")
    if args.migrate_image_grading_direct_upload:
        try:
            from migrate_image_grading_direct_upload import migrate as mig_img_direct
            mig_img_direct(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_image_grading_direct_upload: {e}")
    if args.migrate_image_grading_nullable_columns:
        try:
            from migrate_image_grading_nullable_columns import migrate as mig_img_nullable
            mig_img_nullable(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_image_grading_nullable_columns: {e}")
    if args.migrate_missing_roles:
        try:
            from migrate_missing_roles import migrate_missing_roles
            migrate_missing_roles(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_missing_roles: {e}")
            
    if args.migrate_encounter_files_lab_unit:
        try:
            migrate_encounter_files_lab_unit(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to run migrate_encounter_files_lab_unit: {e}")
            
    if args.migrate_user_disease_specializations:
        try:
            from migrate_user_disease_specializations import migrate
            migrate(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_user_disease_specializations: {e}")
            
    if args.migrate_core_diseases:
        try:
            from migrate_core_diseases import migrate as migrate_core
            migrate_core(dry_run=args.check_only)
        except Exception as e:
            print(f"Failed to import migrate_core_diseases: {e}")

def migrate_user_disease_specializations(dry_run: bool = False) -> None:
    """Create user_disease_specializations table."""
    print("Preparing to create user_disease_specializations table...")
    try:
        from migrate_user_disease_specializations import migrate
        if not dry_run:
            migrate()
        else:
            print("Dry run: Would create user_disease_specializations table")
    except Exception as e:
        print(f"Failed to import migrate_user_disease_specializations: {e}")

def migrate_encounter_files_lab_unit(dry_run: bool = False) -> None:
    """Add lab_unit_id column to encounter_files table."""
    print("Preparing to add lab_unit_id column to encounter_files table...")
    try:
        from migrate_encounter_files_lab_unit import migrate
        if not dry_run:
            migrate()
        else:
            print("Dry run: Would add lab_unit_id column to encounter_files table")
    except Exception as e:
        print(f"Failed to import migrate_encounter_files_lab_unit: {e}")


if __name__ == "__main__":
    _maybe_backup_sqlite(engine)
    main()
