#!/usr/bin/env python3
"""
Backfill script for populating GradingTask.uuid on existing rows.

Usage:
    uv run python -m scripts.backfill_task_uuid

Optional flags:
    --dry-run   Perform all calculations but do not commit changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sqlalchemy import or_

# Ensure project root is importable when invoked as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import Session, GradingTask  # noqa: E402  (import after sys.path manipulation)


def iter_missing_tasks(batch_size: int = 500) -> Iterable[list[GradingTask]]:
    """Yield batches of tasks missing UUIDs to avoid loading everything at once."""
    with Session() as db:
        offset = 0
        while True:
            batch = (
                db.query(GradingTask)
                .filter(or_(GradingTask.uuid.is_(None), GradingTask.uuid == ""))
                .order_by(GradingTask.id)
                .offset(offset)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            yield batch
            offset += len(batch)


def backfill_task_uuids(*, dry_run: bool = False, batch_size: int = 500) -> int:
    """
    Assign uuid4 values to every GradingTask missing one.

    Returns the number of rows updated.
    """
    total_updated = 0

    with Session() as db:
        while True:
            batch = (
                db.query(GradingTask)
                .filter(or_(GradingTask.uuid.is_(None), GradingTask.uuid == ""))
                .order_by(GradingTask.id)
                .limit(batch_size)
                .all()
            )

            if not batch:
                break

            for task in batch:
                task.uuid = str(uuid4())
            total_updated += len(batch)

            if dry_run:
                db.rollback()
                break

            db.commit()

    return total_updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate missing GradingTask UUIDs.")
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
    args = parser.parse_args()

    updated = backfill_task_uuids(dry_run=args.dry_run, batch_size=args.batch_size)
    if args.dry_run:
        print(f"[DRY RUN] Would update {updated} grading_tasks.")
    else:
        print(f"✅ Updated {updated} grading_tasks with UUIDs.")


if __name__ == "__main__":
    main()
