"""annotations stage: COCO-style rows, one per annotation instance, with images and categories.

Conversion (bbox, area, polygon / RLE segmentation) reuses ``datasets.annotation_export`` so these rows agree
with the COCO files produced elsewhere. Geometry that cannot be converted is kept with a warning, not dropped.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from datasets.annotation_export import coco_annotation, coco_class_name, serialize_annotation_set
from grading.workbench.models import AnnotationInstance, AnnotationSet

from .tables import BuildContext, _chunks, _image_properties, _json


def _annotation_sets(ctx: BuildContext) -> dict:
    grade_ids = [grade.id for bundle in ctx.bundles for grade in bundle.grades]
    found = {}
    for chunk in _chunks(grade_ids):
        for annotation_set in ctx.db.execute(
            select(AnnotationSet).where(AnnotationSet.grade_id.in_(chunk))
            .options(selectinload(AnnotationSet.instances).selectinload(AnnotationInstance.mask_tiles))
        ).scalars():
            found[annotation_set.grade_id] = annotation_set
    return found


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    sets = _annotation_sets(ctx)
    image_rows = {}
    uuids = []
    for encounter_id, items in ctx.media.items():
        for kind, row in items:
            image_rows[row.uuid] = (ctx.encounter_uuid[encounter_id], row, kind)
            uuids.append(row.uuid)
    for row in ctx.direct_uploads:
        image_rows[row.uuid] = (None, row, "direct_image_upload")
        uuids.append(row.uuid)
    dims = _image_properties(ctx.db, uuids)

    def file_name(uuid: str) -> str:
        row = image_rows.get(uuid)
        ext = (str(getattr(row[1], "original_filename", None) or getattr(row[1], "filename", None) or "").rsplit(".", 1)
               [-1].lower() if row else "") or "jpg"
        return f"{uuid}.{ext if len(ext) <= 5 else 'jpg'}"

    collected = []  # (bundle, grade, instance dict, width, height)
    for bundle in ctx.bundles:
        for grade in bundle.grades:
            annotation_set = sets.get(grade.id)
            if annotation_set is None:
                continue
            serialized = serialize_annotation_set(annotation_set)
            for instance in serialized["instances"]:
                if instance["geometry_type"] == "none":
                    continue
                prop = dims.get(instance["image_uuid"])
                width = serialized.get("source_image_width") or (prop.width if prop else None)
                height = serialized.get("source_image_height") or (prop.height if prop else None)
                collected.append((bundle, grade, instance, width, height))

    names = sorted({coco_class_name(instance) for _, _, instance, _, _ in collected})
    category_ids = {name: index for index, name in enumerate(names, 1)}
    per_category, per_image = Counter(), Counter()
    annotations = []
    for index, (bundle, grade, instance, width, height) in enumerate(collected, 1):
        name = coco_class_name(instance)
        converted, warning = None, None
        if not width or not height:
            warning = "image dimensions unknown"
        else:
            try:
                converted = coco_annotation(instance, width, height)
            except (TypeError, ValueError, OSError):
                converted = None
            if converted is None:
                warning = "invalid annotation geometry"
        bbox = converted["bbox"] if converted else [None] * 4
        image_uuid = instance["image_uuid"]
        per_category[name] += 1
        per_image[image_uuid] += 1
        annotations.append({
            "annotation_id": index, "image_uuid": image_uuid, "file_name": file_name(image_uuid),
            "width": width, "height": height, "encounter_uuid": ctx.encounter_uuid.get(bundle.encounter_id),
            "category_id": category_ids[name], "category_name": name,
            "bbox_x": bbox[0], "bbox_y": bbox[1], "bbox_w": bbox[2], "bbox_h": bbox[3],
            "area": converted["area"] if converted else None, "iscrowd": 0,
            "segmentation": _json(converted["segmentation"]) if converted else None,
            "geometry_type": instance["geometry_type"], "instance_uuid": instance["uuid"],
            "source_task_uuid": bundle.task.uuid, "source_grade_id": grade.id, "source_role_slot": grade.role_slot,
            "source_grader_user_id": grade.grader_user_id,
            "source_grader_username": grade.grader.username if grade.grader else None,
            "source_grade": grade.grade_name,
            "source_disease": bundle.task.disease.name if bundle.task.disease else None,
            "source_graded_at": grade.updated_at or grade.created_at, "warning": warning,
        })
    tasks_per_image = Counter(bundle.image_uuid for bundle in ctx.bundles if bundle.image_uuid)
    images = []
    for uuid, (encounter_uuid, _row, _kind) in image_rows.items():
        prop = dims.get(uuid)
        images.append({
            "image_uuid": uuid, "file_name": file_name(uuid),
            "width": prop.width if prop else None, "height": prop.height if prop else None,
            "encounter_uuid": encounter_uuid, "task_count": tasks_per_image.get(uuid, 0),
            "annotation_count": per_image.get(uuid, 0),
        })
    return {
        "coco_annotations": annotations,
        "coco_categories": [
            {"category_id": category_ids[name], "category_name": name, "annotation_count": per_category[name]}
            for name in names
        ],
        "coco_images": images,
    }
