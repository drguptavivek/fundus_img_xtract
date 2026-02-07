#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging

from sqlalchemy import and_, func, select

from db_transaction_manager import transaction_scope
from models import DirectImageUpload, Disease, EncounterFile, GradingTask
from services.taskCreationServices import _is_verified_for_disease, create_or_get_task
from utils.linkedGradingUtils import get_linked_disease_ids
from utils.log_sanitize import sanitize_log_value


LOGGER = logging.getLogger("linked_task_backfill")


def _get_dr_disease_id(db) -> int | None:
    row = (
        db.execute(
            select(Disease.id)
            .where(func.lower(Disease.name).in_(["diabetic retinopathy", "dr"]))
            .order_by(Disease.id)
        )
        .first()
    )
    return row[0] if row else None


def _iter_dr_tasks(db, dr_id: int, limit: int | None):
    remaining = limit
    encounter_query = (
        db.query(GradingTask)
        .filter(
            GradingTask.disease_id == dr_id,
            GradingTask.encounter_file_id.is_not(None),
            GradingTask.state == "pending",
        )
    )
    for task in encounter_query.all() if remaining is None else encounter_query.limit(remaining).all():
        yield task, "encounter"
        if remaining is not None:
            remaining -= 1
            if remaining <= 0:
                return

    direct_query = (
        db.query(GradingTask)
        .filter(
            GradingTask.disease_id == dr_id,
            GradingTask.direct_image_upload_id.is_not(None),
            GradingTask.state == "pending",
        )
    )
    for task in direct_query.all() if remaining is None else direct_query.limit(remaining).all():
        yield task, "direct"
        if remaining is not None:
            remaining -= 1
            if remaining <= 0:
                return


def _resolve_image(db, task: GradingTask, kind: str) -> tuple[int, str | None]:
    if kind == "encounter":
        ef = db.get(EncounterFile, task.encounter_file_id)
        return (ef.id if ef else None, ef.uuid if ef else None)
    diu = db.get(DirectImageUpload, task.direct_image_upload_id)
    return (diu.id if diu else None, diu.uuid if diu else None)


def backfill_linked_tasks(*, apply_changes: bool, limit: int | None) -> int:
    stats = {
        "primary_tasks": 0,
        "verified_primary": 0,
        "unverified_primary": 0,
        "missing_linked": 0,
        "created_linked": 0,
        "existing_linked": 0,
        "errors": 0,
    }

    with transaction_scope() as db:
        dr_id = _get_dr_disease_id(db)
        if not dr_id:
            LOGGER.error("DR disease not found. Exiting.")
            return 1

        linked_ids = get_linked_disease_ids(db, dr_id)
        if not linked_ids:
            LOGGER.info("No active linked diseases for DR. Exiting.")
            return 0

        for task, kind in _iter_dr_tasks(db, dr_id, limit):
            stats["primary_tasks"] += 1
            image_id, image_uuid = _resolve_image(db, task, kind)
            if not image_id:
                stats["errors"] += 1
                LOGGER.warning(
                    "Skipping task %s: missing image reference.",
                    sanitize_log_value(task.id),
                )
                continue

            if not _is_verified_for_disease(db, kind, image_id, dr_id):
                stats["unverified_primary"] += 1
                continue

            stats["verified_primary"] += 1

            for linked_id in linked_ids:
                existing = db.execute(
                    select(GradingTask.id).where(
                        and_(
                            GradingTask.disease_id == linked_id,
                            (
                                GradingTask.encounter_file_id == image_id
                                if kind == "encounter"
                                else GradingTask.direct_image_upload_id == image_id
                            ),
                        )
                    )
                ).first()

                if existing:
                    stats["existing_linked"] += 1
                    continue

                stats["missing_linked"] += 1
                if not apply_changes:
                    continue

                try:
                    create_or_get_task(
                        db,
                        kind=kind,
                        image_id=image_id if kind != "encounter_set" else None,
                        disease_id=linked_id,
                        lab_unit_id=task.lab_unit_id,
                        create_linked=False,
                    )
                    stats["created_linked"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    LOGGER.exception(
                        "Failed to create linked task for image %s (task %s): %s",
                        sanitize_log_value(image_uuid or image_id),
                        sanitize_log_value(task.id),
                        sanitize_log_value(exc),
                    )

    LOGGER.info(
        "Linked task backfill complete. primary=%s verified=%s unverified=%s missing=%s created=%s existing=%s errors=%s",
        stats["primary_tasks"],
        stats["verified_primary"],
        stats["unverified_primary"],
        stats["missing_linked"],
        stats["created_linked"],
        stats["existing_linked"],
        stats["errors"],
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill linked tasks for DR primary tasks (encounter + direct)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default: dry-run).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of primary DR tasks processed.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not args.apply:
        LOGGER.info("Dry-run mode. Use --apply to create linked tasks.")
    return backfill_linked_tasks(apply_changes=args.apply, limit=args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
