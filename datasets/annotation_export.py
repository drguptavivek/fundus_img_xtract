"""Native, lossless annotation companion for curated dataset exports."""

import base64
import json
import math
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

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
                    "annotation_set": serialize_annotation_set(annotation_set) if annotation_set else None,
                })

    manifest = {
        "schema_version": 1,
        "tasks": [
            {
                "task_uuid": row["task_uuid"],
                "image_uuid": row["image_uuid"],
                "image_filename": row["image_filename"],
                "disease": row["disease"],
                "final_grade": row.get("final_impression"),
                "grades": by_task[int(row["task_id"])],
            }
            for row in rows
        ],
    }
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def serialize_annotation_set(annotation_set):
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


_ROLE_PRIORITY = {
    "regrade_adj": 5,
    "arbitrator": 4,
    "review": 3,
    "resident2": 2,
    "resident": 1,
}


def write_annotator_exports(manifest: dict, exported_images: dict, export_dir: Path) -> None:
    """Keep each saved human or AI grade separate for multi-annotator analysis."""
    records = []
    records_by_image = {}
    for task in manifest["tasks"]:
        image_uuid = task["image_uuid"]
        image = exported_images.get(image_uuid)
        for grade in task["grades"]:
            record = {
                "task_uuid": task["task_uuid"],
                "image_uuid": image_uuid,
                "image_filename": image["file_name"] if image else task["image_filename"],
                "image_in_zip": image is not None,
                "disease": task["disease"],
                "dataset_final_grade": task.get("final_grade"),
                **grade,
            }
            records.append(record)
            if image is not None:
                records_by_image.setdefault(image_uuid, []).append(record)
    _write_jsonl(export_dir / "annotator_submissions.jsonl", records)
    sidecars_by_zip = {}
    for image_uuid, image in exported_images.items():
        sidecar = str(Path(image["file_name"]).with_suffix(".annotators.jsonl"))
        sidecars_by_zip.setdefault(image["zip_path"], []).append(
            (sidecar, records_by_image.get(image_uuid, []))
        )
    for zip_path, sidecars in sidecars_by_zip.items():
        with ZipFile(zip_path, "a") as archive:
            for sidecar, image_records in sidecars:
                archive.writestr(
                    sidecar,
                    "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in image_records),
                )


def write_coco_exports(manifest: dict, exported_images: dict, export_dir: Path) -> list[str]:
    """Write IITK image JSONL, COCO JSON/JSONL, and adjacent COCO sidecars."""
    warnings = []
    tasks_by_image = {}
    for task in manifest["tasks"]:
        tasks_by_image.setdefault(task["image_uuid"], []).append(task)

    source_instances = {}
    class_names = set()
    for image_uuid, image in sorted(exported_images.items()):
        collected = []
        for task in tasks_by_image.get(image_uuid, []):
            grade = _selected_human_grade(task["grades"])
            if not grade or not grade.get("annotation_set"):
                continue
            annotation_set = grade["annotation_set"]
            source_width = annotation_set.get("source_image_width")
            source_height = annotation_set.get("source_image_height")
            if (source_width is not None and source_width != image["width"]) or (
                source_height is not None and source_height != image["height"]
            ):
                warnings.append(f"Task {task['task_uuid']}: annotation image dimensions differ, skipped in COCO")
                continue
            for instance in annotation_set["instances"]:
                if instance["image_uuid"] != image_uuid:
                    warnings.append(f"Task {task['task_uuid']}: annotation image mismatch, skipped in COCO")
                    continue
                if instance["geometry_type"] == "none":
                    continue
                cls = coco_class_name(instance)
                class_names.add(cls)
                collected.append((task, grade, instance, cls))
        source_instances[image_uuid] = collected

    category_ids = {name: index for index, name in enumerate(sorted(class_names), 1)}
    categories = [{"id": category_ids[name], "name": name} for name in sorted(class_names)]
    coco_images = []
    coco_annotations = []
    jsonl_records = []
    coco_records = []
    for image_id, (image_uuid, image) in enumerate(sorted(exported_images.items()), 1):
        width, height = image["width"], image["height"]
        coco_image = {
            "id": image_id, "file_name": image["file_name"],
            "width": width, "height": height,
        }
        coco_images.append(coco_image)
        annotations = []
        boxes = []
        task_grades = []
        for task in tasks_by_image.get(image_uuid, []):
            highest_grade = _highest_human_grade(task["grades"])
            annotated_grade = _selected_human_grade(task["grades"])
            task_grades.append({
                "task_uuid": task["task_uuid"],
                "disease": task["disease"],
                "dataset_final_grade": task.get("final_grade"),
                "highest_human_grade": highest_grade["grade_name"] if highest_grade else None,
                "highest_human_role_slot": highest_grade["role_slot"] if highest_grade else None,
                "annotation_source_role_slot": annotated_grade["role_slot"] if annotated_grade else None,
            })
        for task, grade, instance, cls in source_instances[image_uuid]:
            try:
                converted = coco_annotation(instance, width, height)
            except (TypeError, ValueError, OSError):
                converted = None
            if converted is None:
                warnings.append(f"Task {task['task_uuid']}: invalid annotation geometry skipped in COCO")
                continue
            annotation = {
                "id": len(coco_annotations) + 1,
                "image_id": image_id,
                "category_id": category_ids[cls],
                "bbox": converted["bbox"],
                "area": converted["area"],
                "segmentation": converted["segmentation"],
                "iscrowd": 0,
                "source_task_uuid": task["task_uuid"],
                "source_role_slot": grade["role_slot"],
                "annotation_source_grade": grade["grade_name"],
                "task_final_grade": task.get("final_grade"),
            }
            annotations.append(annotation)
            coco_annotations.append(annotation)
            x, y, w, h = converted["bbox"]
            boxes.append({"x": x, "y": y, "w": w, "h": h, "cls": cls})
        jsonl_records.append({
            "schema": "aiims-eom-v1",
            "sessionId": image.get("encounter_uuid"),
            "labeler": "fundus-workbench",
            "filename": Path(image["file_name"]).name,
            "file_name": image["file_name"],
            "image_uuid": image_uuid,
            "labels": {"boxes": boxes},
            "task_grades": task_grades,
        })
        coco_records.append({
            "image": coco_image, "annotations": annotations,
            "categories": categories, "task_grades": task_grades,
        })

    _write_jsonl(export_dir / "annotations.jsonl", jsonl_records)
    _write_jsonl(export_dir / "coco.jsonl", coco_records)
    (export_dir / "coco.json").write_text(json.dumps({
        "info": {"description": "Curated workbench annotation export"},
        "licenses": [], "images": coco_images,
        "annotations": coco_annotations, "categories": categories,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    sidecars_by_zip = {}
    for record, image in zip(coco_records, (exported_images[k] for k in sorted(exported_images))):
        sidecar = str(Path(image["file_name"]).with_suffix(".coco.jsonl"))
        sidecars_by_zip.setdefault(image["zip_path"], []).append((sidecar, record))
    for zip_path, sidecars in sidecars_by_zip.items():
        with ZipFile(zip_path, "a") as archive:
            for sidecar, record in sidecars:
                archive.writestr(sidecar, json.dumps(record, ensure_ascii=False) + "\n")
    return warnings


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


def _selected_human_grade(grades: list[dict]) -> dict | None:
    eligible = [
        grade for grade in grades
        if grade["role_slot"] in _ROLE_PRIORITY
        and grade.get("annotation_set")
        and any(
            instance.get("geometry_type") != "none"
            for instance in grade["annotation_set"].get("instances", [])
        )
    ]
    return max(eligible, key=lambda grade: (_ROLE_PRIORITY[grade["role_slot"]], grade["grade_id"])) if eligible else None


def _highest_human_grade(grades: list[dict]) -> dict | None:
    eligible = [grade for grade in grades if grade["role_slot"] in _ROLE_PRIORITY]
    return max(eligible, key=lambda grade: (_ROLE_PRIORITY[grade["role_slot"]], grade["grade_id"])) if eligible else None


def coco_class_name(instance: dict) -> str:
    key = instance.get("class_key") or ""
    if instance.get("class_source") == "project_class" and re.fullmatch(r"[a-z][a-z0-9_]*", key):
        return key
    label = instance.get("class_label") or key
    name = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return name or "unlabeled"


def coco_annotation(instance: dict, width: int, height: int) -> dict | None:
    bbox = instance.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        x, y, w, h = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (x, y, w, h)) or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        return None
    geometry = instance.get("geometry") or {}
    polygon = geometry.get("polygon") or {}
    points = polygon.get("pixel") if isinstance(polygon, dict) else None
    segmentation = []
    area = w * h
    if instance.get("mask_tiles"):
        segmentation, area = _mask_rle(instance["mask_tiles"], width, height)
    elif instance.get("geometry_type") in {"polygon", "ellipse", "pyramid"} and isinstance(points, list) and len(points) >= 3:
        try:
            coords = [(float(point[0]), float(point[1])) for point in points]
        except (TypeError, ValueError, IndexError):
            return None
        if not all(math.isfinite(px) and math.isfinite(py) and 0 <= px <= width and 0 <= py <= height for px, py in coords):
            return None
        segmentation = [[value for point in coords for value in point]]
        area = abs(sum(coords[i][0] * coords[(i + 1) % len(coords)][1] - coords[(i + 1) % len(coords)][0] * coords[i][1] for i in range(len(coords)))) / 2
    if area <= 0:
        return None
    return {"bbox": [x, y, w, h], "area": area, "segmentation": segmentation}


def _mask_rle(tiles: list[dict], width: int, height: int) -> tuple[dict, int]:
    mask = bytearray(width * height)
    for tile in tiles:
        origin_x, origin_y = tile["tile_x"] * 256, tile["tile_y"] * 256
        if origin_x + tile["width"] > width or origin_y + tile["height"] > height:
            raise ValueError("Mask tile extends beyond the exported image")
        with Image.open(BytesIO(base64.b64decode(tile["png_base64"]))) as png:
            if png.size != (tile["width"], tile["height"]):
                raise ValueError("Mask tile dimensions changed")
            pixels = (png.getchannel("A") if "A" in png.getbands() else png.convert("L")).tobytes()
        for tile_y in range(tile["height"]):
            offset = (origin_y + tile_y) * width + origin_x
            row = pixels[tile_y * tile["width"]:(tile_y + 1) * tile["width"]]
            mask[offset:offset + tile["width"]] = bytes(1 if value else 0 for value in row)
    counts = []
    current = 0
    run = 0
    for x in range(width):
        for y in range(height):
            value = mask[y * width + x]
            if value == current:
                run += 1
            else:
                counts.append(run)
                current = value
                run = 1
    counts.append(run)
    return {"size": [height, width], "counts": counts}, mask.count(1)
