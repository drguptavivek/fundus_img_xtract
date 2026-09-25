"""Native, lossless annotation companion for curated dataset exports."""

import base64
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_transaction_manager import get_db_session
from grading.workbench.models import AnnotationInstance, AnnotationSet
from models import Grade


def write_annotation_export(rows, destination: Path) -> Path:
    """Export only grades owned by the worker-authorized dataset task rows."""
    task_ids = {int(row["task_id"]) for row in rows}
    by_task = {task_id: [] for task_id in task_ids}
    if task_ids:
        with get_db_session() as db:
            grades = db.execute(
                select(Grade)
                .where(Grade.task_id.in_(task_ids))
                .order_by(Grade.task_id, Grade.id)
            ).scalars().all()
            grade_ids = [grade.id for grade in grades]
            sets = (
                db.execute(
                    select(AnnotationSet)
                    .options(
                        selectinload(AnnotationSet.instances).selectinload(
                            AnnotationInstance.mask_tiles
                        )
                    )
                    .where(AnnotationSet.grade_id.in_(grade_ids))
                ).scalars().all()
                if grade_ids else []
            )
            sets_by_grade = {item.grade_id: item for item in sets}
            for grade in grades:
                annotation_set = sets_by_grade.get(grade.id)
                by_task[grade.task_id].append({
                    "grade_id": grade.id,
                    "role_slot": grade.role_slot,
                    "grade_name": grade.grade_name,
                    "selected_features": json.loads(grade.selected_features_json)
                    if grade.selected_features_json else None,
                    "feature_geometry": grade.feature_geometry_json,
                    "annotation_set": _serialize_set(annotation_set) if annotation_set else None,
                })

    manifest = {
        "schema_version": 1,
        "tasks": [
            {
                "task_uuid": row["task_uuid"],
                "image_uuid": row["image_uuid"],
                "image_filename": row["image_filename"],
                "disease": row["disease"],
                "grades": by_task[int(row["task_id"])],
            }
            for row in rows
        ],
    }
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _serialize_set(annotation_set):
    return {
        "uuid": annotation_set.uuid,
        "schema_version": annotation_set.schema_version,
        "policy_source": annotation_set.policy_source,
        "policy_revision": annotation_set.policy_revision,
        "source_image_width": annotation_set.source_image_width,
        "source_image_height": annotation_set.source_image_height,
        "instances": [
            {
                "uuid": instance.uuid,
                "image_uuid": instance.image_uuid,
                "class_source": instance.class_source,
                "grading_feature_id": instance.grading_feature_id,
                "project_class_id": instance.project_class_id,
                "class_key": instance.class_key_snapshot,
                "class_label": instance.class_label_snapshot,
                "policy_revision": instance.policy_revision,
                "geometry_type": instance.geometry_type,
                "geometry": instance.geometry_json,
                "bbox": [instance.bbox_x, instance.bbox_y, instance.bbox_w, instance.bbox_h],
                "instance_order": instance.instance_order,
                "locked": instance.locked,
                "mask_tiles": [
                    {
                        "tile_x": tile.tile_x,
                        "tile_y": tile.tile_y,
                        "width": tile.width,
                        "height": tile.height,
                        "checksum": tile.checksum,
                        "png_base64": base64.b64encode(tile.png_bytes).decode("ascii"),
                    }
                    for tile in sorted(instance.mask_tiles, key=lambda t: (t.tile_y, t.tile_x))
                ],
            }
            for instance in sorted(annotation_set.instances, key=lambda i: (i.instance_order, i.id))
        ],
    }
