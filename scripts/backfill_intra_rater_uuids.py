#!/usr/bin/env python3
"""
Backfill script for populating IntraRaterTask.uuid on existing rows.

Usage:
    uv run scripts/backfill_intra_rater_uuids.py

Optional flags:
    --dry-run   Perform all calculations but do not commit changes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sqlalchemy import or_

# Ensure project root is importable when invoked as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import Session, IntraRaterTask  # noqa: E402  (import after sys.path manipulation)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def iter_missing_tasks(batch_size: int = 500) -> Iterable[list[IntraRaterTask]]:
    """Yield batches of IntraRaterTask records missing UUIDs to avoid loading everything at once."""
    with Session() as db:
        offset = 0
        while True:
            batch = (
                db.query(IntraRaterTask)
                .filter(or_(IntraRaterTask.uuid.is_(None), IntraRaterTask.uuid == ""))
                .order_by(IntraRaterTask.id)
                .offset(offset)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            yield batch
            offset += len(batch)


def backfill_intra_rater_uuids(*, dry_run: bool = False, batch_size: int = 500) -> int:
    """
    Assign uuid4 values to every IntraRaterTask missing one.

    Returns the number of rows updated.
    """
    total_updated = 0

    with Session() as db:
        while True:
            batch = (
                db.query(IntraRaterTask)
                .filter(or_(IntraRaterTask.uuid.is_(None), IntraRaterTask.uuid == ""))
                .order_by(IntraRaterTask.id)
                .limit(batch_size)
                .all()
            )

            if not batch:
                break

            for task in batch:
                task.uuid = str(uuid4())
                logger.debug(f"Assigned UUID {task.uuid} to IntraRaterTask ID {task.id}")
            
            total_updated += len(batch)
            logger.info(f"Processing batch of {len(batch)} IntraRaterTask records")

            if dry_run:
                db.rollback()
                logger.info(f"[DRY RUN] Would update {total_updated} IntraRaterTask records with UUIDs.")
                break

            try:
                db.commit()
                logger.info(f"Successfully committed batch of {len(batch)} records")
            except Exception as e:
                logger.error(f"Error committing batch: {e}")
                db.rollback()
                raise

    return total_updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate missing IntraRaterTask UUIDs.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without committing changes.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of rows to update per transaction (default: 500).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting IntraRaterTask UUID backfill process")
    
    try:
        updated = backfill_intra_rater_uuids(dry_run=args.dry_run, batch_size=args.batch_size)
        if args.dry_run:
            logger.info(f"[DRY RUN] Would update {updated} IntraRaterTask records with UUIDs.")
        else:
            logger.info(f"✅ Successfully updated {updated} IntraRaterTask records with UUIDs.")
    except Exception as e:
        logger.error(f"Error during backfill process: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()