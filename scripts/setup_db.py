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

# Ensure project root is importable when running this script directly
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Ensure env is loaded (DATABASE_URL, etc.)
load_dotenv()

from models import Base, engine  # noqa: E402


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
        "--migrate-anonymization-verifications",
        action="store_true",
        help="Create tables for direct image anonymization verifications feature",
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


if __name__ == "__main__":
    main()
