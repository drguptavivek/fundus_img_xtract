from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import (
    CuratedDataset,
    CuratedDatasetItem,
    DirectImageUpload,
    EncounterFile,
    GradingTask,
    IMAGE_DIR,
    ImagePiiVerification,
    PatientEncounters,
    ZipFile,
)
from utils.utils import with_session
from auth.utils import utcnow
from utils.fileUtils import abs_from_parts
from utils.ocr_pii import detect_pii_details_for_path


@dataclass(frozen=True)
class ImageInfo:
    image_uuid: str
    variant: str
    path: str


def _resolve_image_info(db, task: GradingTask) -> Optional[ImageInfo]:
    if task.encounter_file_id:
        encounter = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.id == task.encounter_file_id)
            .first()
        )
        if not encounter:
            return None
        encounter_file, patient_encounter, zip_file = encounter
        if not encounter_file or not encounter_file.filename:
            return None
        upload_date = zip_file.upload_date if zip_file else None
        if not upload_date:
            return None
        upload_date_str = upload_date.strftime("%Y_%m_%d")
        image_uuid = encounter_file.uuid
        image_path = str(IMAGE_DIR / upload_date_str / encounter_file.filename)
        return ImageInfo(image_uuid=image_uuid, variant="orig", path=image_path)

    if task.direct_image_upload_id:
        direct = db.query(DirectImageUpload).filter(DirectImageUpload.id == task.direct_image_upload_id).first()
        if not direct or not direct.filename:
            return None
        filename = direct.edited_filename or direct.filename
        variant = "edited" if direct.edited_filename else "orig"
        image_path = str(abs_from_parts(direct.folder_rel, filename, variant))
        return ImageInfo(image_uuid=direct.uuid, variant=variant, path=image_path)

    return None


def backfill_pii_for_dataset(
    dataset_name: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> int:
    with with_session() as db:
        return _backfill_pii_for_dataset(db, dataset_name, dry_run=dry_run, limit=limit)


def _backfill_pii_for_dataset(
    db,
    dataset_name: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> int:
    dataset = db.query(CuratedDataset).filter(CuratedDataset.name == dataset_name).first()
    if not dataset:
        print(f"Dataset not found: {dataset_name}", file=sys.stderr)
        return 0

    query = (
        db.query(CuratedDatasetItem, GradingTask)
        .join(GradingTask, CuratedDatasetItem.task_id == GradingTask.id)
        .filter(CuratedDatasetItem.dataset_id == dataset.id)
        .order_by(CuratedDatasetItem.id.asc())
    )
    if limit:
        query = query.limit(limit)

    created = 0
    for item, task in query:
        step_start = time.perf_counter()
        info = _resolve_image_info(db, task)
        if not info:
            print("Skipping: unable to resolve image info", file=sys.stderr)
            continue
        existing = (
            db.query(ImagePiiVerification)
            .filter(
                ImagePiiVerification.image_uuid == info.image_uuid,
                ImagePiiVerification.image_variant == info.variant,
            )
            .first()
        )
        if existing and existing.source == "manual":
            print(
                f"Skip manual override {info.image_uuid} ({info.variant})",
                file=sys.stderr,
            )
            continue
        if existing:
            print(
                f"Skip existing {info.image_uuid} ({info.variant}) status={existing.pii_status} source={existing.source}",
                file=sys.stderr,
            )
            continue
        if dry_run:
            elapsed = time.perf_counter() - step_start
            print(f"Dry-run missing {info.image_uuid} ({info.variant}) in {elapsed:.2f}s", file=sys.stderr)
            created += 1
            continue
        try:
            print(f"Detecting {info.image_uuid} ({info.variant})", file=sys.stderr)
            ocr_start = time.perf_counter()
            ocr_result = detect_pii_details_for_path(info.path)
            ocr_elapsed = time.perf_counter() - ocr_start
        except Exception as exc:
            elapsed = time.perf_counter() - step_start
            print(
                f"Skipping {info.image_uuid} ({info.variant}) after {elapsed:.2f}s: {exc}",
                file=sys.stderr,
            )
            continue
        status = "detected" if ocr_result.get("is_pii") else "clear"
        print(
            f"Result {info.image_uuid} ({info.variant}) status={status} "
            f"valid={ocr_result.get('valid_detections', 0)} "
            f"patterns={ocr_result.get('pattern_matches', 0)} "
            f"ocr_time={ocr_elapsed:.2f}s",
            file=sys.stderr,
        )
        db.add(
            ImagePiiVerification(
                image_uuid=info.image_uuid,
                image_variant=info.variant,
                pii_status=status,
                source="auto",
                detections_json=json.dumps(ocr_result.get("detections", [])),
                roi_json=json.dumps(ocr_result.get("roi")) if ocr_result.get("roi") else None,
                checked_at=utcnow(),
            )
        )
        created += 1
        elapsed = time.perf_counter() - step_start
        print(f"Stored {info.image_uuid} ({info.variant}) total_time={elapsed:.2f}s", file=sys.stderr)
        time.sleep(3)

    message = f"New PII rows to create: {created}" if dry_run else f"Created PII rows: {created}"
    print(message, file=sys.stderr)
    return created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill PII status for a curated dataset.")
    parser.add_argument(
        "--dataset-name",
        default="MIDAS_Glaucoma_1",
        help="Curated dataset name to backfill.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only count missing rows.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items processed.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    backfill_pii_for_dataset(args.dataset_name, dry_run=args.dry_run, limit=args.limit)
