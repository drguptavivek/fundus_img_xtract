"""Scoped inventory, sidecars and per-object authorization for sync clients.

Everything here takes a :class:`SyncContext` produced by
``service.authenticate_credential`` and never widens it. Identifier-bearing
fields and PII-flagged media are only returned for Lab Units in
``ctx.pii_lab_unit_ids``.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from flask import current_app
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from datasets.annotation_export import coco_annotation, coco_class_name, serialize_annotation_set
from grading.workbench.models import AnnotationInstance, AnnotationSet
from media.authorization import (
    AuthorizedMediaSource,
    MediaResolutionError,
    MediaSourceType,
    resolve_media_source,
)
from models import (
    Consensus,
    DirectImageUpload,
    Disease,
    EncounterFile,
    EncounterFilePDF,
    EncounterSetGradingPackage,
    EncounterSetImage,
    Grade,
    GradingTask,
    ImageMetadata,
    ImagePiiVerification,
    LabUnit,
    PatientEncounters,
    User,
)

from .dto import SyncContext
from .exceptions import ProjectSyncNotFound, ProjectSyncValidationError

MAX_ENCOUNTER_PAGE = 200
MAX_DIRECT_PAGE = 500
MAX_SIDECAR_BATCH = 50
SIDECAR_SCHEMA = "fundus-sync-v1"

KIND_ENCOUNTER_FILE = "encounter_file"
KIND_ENCOUNTER_SET_IMAGE = "encounter_set_image"
KIND_ENCOUNTER_FILE_PDF = "encounter_file_pdf"
KIND_DIRECT_IMAGE = "direct_image_upload"

SYNC_MEDIA_SOURCES = frozenset(
    {
        MediaSourceType.ENCOUNTER_FILE,
        MediaSourceType.ENCOUNTER_SET_IMAGE,
        MediaSourceType.ENCOUNTER_FILE_PDF,
        MediaSourceType.DIRECT_IMAGE_UPLOAD,
    }
)
VARIANTS = frozenset({"original", "edited"})


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    ext = filename.rsplit(".", 1)[1].lower()
    return ext if ext.isalnum() and len(ext) <= 8 else ""


def parse_page(after_id, limit, *, maximum: int) -> tuple[int, int]:
    try:
        after = int(after_id or 0)
        size = int(limit or maximum)
    except (TypeError, ValueError) as exc:
        raise ProjectSyncValidationError("after_id and limit must be integers.") from exc
    if after < 0 or size < 1:
        raise ProjectSyncValidationError("after_id must be >= 0 and limit >= 1.")
    return after, min(size, maximum)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


def describe_context(db, ctx: SyncContext) -> dict:
    labs = db.execute(
        select(LabUnit.id, LabUnit.name).where(LabUnit.id.in_(ctx.lab_unit_ids)).order_by(LabUnit.id)
    ).all()
    return {
        "grant_uuid": ctx.grant_uuid,
        "user": {"id": ctx.user_id, "username": ctx.username},
        "project": {"id": ctx.project_id, "code": ctx.project_code},
        "expires_at": _iso(ctx.expires_at),
        "lab_units": [
            {"id": lab_id, "name": name, "pii": lab_id in ctx.pii_lab_unit_ids} for lab_id, name in labs
        ],
        "sidecar_schema": SIDECAR_SCHEMA,
        "page_limits": {"encounters": MAX_ENCOUNTER_PAGE, "direct_images": MAX_DIRECT_PAGE, "sidecars": MAX_SIDECAR_BATCH},
        "client_policy": {
            "max_concurrency": max(1, int(current_app.config.get("PROJECT_SYNC_MAX_CONCURRENT", 1))),
            "min_interval_ms": max(0, int(current_app.config.get("PROJECT_SYNC_MIN_INTERVAL_MS", 250))),
        },
    }


# ---------------------------------------------------------------------------
# PII helpers
# ---------------------------------------------------------------------------


def _pii_detected_uuids(db, uuids) -> set[str]:
    uuids = [u for u in uuids if u]
    if not uuids:
        return set()
    return set(
        db.execute(
            select(ImagePiiVerification.image_uuid).where(
                ImagePiiVerification.image_uuid.in_(uuids),
                ImagePiiVerification.image_variant == "orig",
                ImagePiiVerification.pii_status == "detected",
            )
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Grading bundles (tasks, grades, consensus, annotations)
# ---------------------------------------------------------------------------


@dataclass
class _TaskBundle:
    task: GradingTask
    encounter_id: int | None
    image_uuid: str | None
    grades: list
    consensus: Consensus | None


def _load_task_bundles(
    db,
    ctx: SyncContext,
    *,
    encounter_ids=(),
    file_ids=(),
    set_image_ids=(),
    direct_ids=(),
    with_annotations: bool,
) -> list[_TaskBundle]:
    clauses = []
    if file_ids:
        clauses.append(GradingTask.encounter_file_id.in_(list(file_ids)))
    if set_image_ids:
        clauses.append(GradingTask.encounter_set_image_id.in_(list(set_image_ids)))
    if direct_ids:
        clauses.append(GradingTask.direct_image_upload_id.in_(list(direct_ids)))
    if encounter_ids:
        clauses.append(GradingTask.patient_encounter_id.in_(list(encounter_ids)))
        clauses.append(EncounterSetGradingPackage.patient_encounter_id.in_(list(encounter_ids)))
    if not clauses:
        return []
    options = [
        selectinload(GradingTask.disease),
        selectinload(GradingTask.encounter_file),
        selectinload(GradingTask.encounter_set_image),
        selectinload(GradingTask.direct_image),
        selectinload(GradingTask.encounter_set_package),
        selectinload(GradingTask.consensus),
    ]
    grade_loader = selectinload(GradingTask.grades).selectinload(Grade.grader)
    options.append(grade_loader)
    tasks = db.execute(
        select(GradingTask)
        .outerjoin(EncounterSetGradingPackage, EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id)
        .options(*options)
        .where(GradingTask.project_id == ctx.project_id, or_(*clauses))
        .order_by(GradingTask.id)
    ).scalars().unique().all()

    grade_ids = [grade.id for task in tasks for grade in task.grades]
    sets_by_grade: dict[int, AnnotationSet] = {}
    if grade_ids:
        query = select(AnnotationSet).where(AnnotationSet.grade_id.in_(grade_ids))
        if with_annotations:
            query = query.options(
                selectinload(AnnotationSet.instances).selectinload(AnnotationInstance.mask_tiles)
            )
        for annotation_set in db.execute(query).scalars().all():
            sets_by_grade[annotation_set.grade_id] = annotation_set
    # Instance count + latest instance edit, so any added, removed or edited
    # annotation changes the sidecar fingerprint even if the set row is untouched.
    instance_stats: dict[int, tuple[int, str | None]] = {}
    if sets_by_grade:
        for set_id, count, latest in db.execute(
            select(
                AnnotationInstance.annotation_set_id,
                func.count(AnnotationInstance.id),
                func.max(AnnotationInstance.updated_at),
            )
            .where(AnnotationInstance.annotation_set_id.in_([s.id for s in sets_by_grade.values()]))
            .group_by(AnnotationInstance.annotation_set_id)
        ).all():
            instance_stats[set_id] = (int(count), _iso(latest))

    bundles = []
    for task in tasks:
        encounter_id = task.patient_encounter_id
        image_uuid = None
        if task.encounter_file is not None:
            encounter_id = task.encounter_file.patient_encounter_id
            image_uuid = task.encounter_file.uuid
        elif task.encounter_set_image is not None:
            encounter_id = task.encounter_set_image.patient_encounter_id
            image_uuid = task.encounter_set_image.uuid
        elif task.direct_image is not None:
            image_uuid = task.direct_image.uuid
        elif encounter_id is None and task.encounter_set_package is not None:
            encounter_id = task.encounter_set_package.patient_encounter_id
        grades = sorted(task.grades, key=lambda g: g.id)
        for grade in grades:
            annotation_set = sets_by_grade.get(grade.id)
            grade._sync_annotation_set = annotation_set  # type: ignore[attr-defined]
            grade._sync_annotation_stats = (  # type: ignore[attr-defined]
                instance_stats.get(annotation_set.id, (0, None)) if annotation_set is not None else None
            )
        bundles.append(_TaskBundle(task, encounter_id, image_uuid, grades, task.consensus))
    return bundles


def _task_record(bundle: _TaskBundle) -> dict:
    task = bundle.task
    consensus = bundle.consensus
    return {
        "record_type": "task",
        "task_uuid": task.uuid,
        "image_uuid": bundle.image_uuid,
        "disease": task.disease.name if task.disease else None,
        "disease_id": task.disease_id,
        "grading_target_level": task.grading_target_level,
        "task_source": task.task_source,
        "state": task.state,
        "lab_unit_id": task.lab_unit_id,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "consensus": {
            "final_grade": consensus.final_grade_name,
            "final_grade_description": consensus.final_grade_description,
            "final_disease": consensus.final_disease_name,
            "method": consensus.method,
            "scope": consensus.consensus_scope,
            "decided_by_user_id": consensus.decided_by_user_id,
            "decided_at": _iso(consensus.decided_at),
        } if consensus else None,
    }


def _grade_record(bundle: _TaskBundle, grade: Grade, *, with_annotations: bool) -> dict:
    annotation_set = getattr(grade, "_sync_annotation_set", None)
    record = {
        "record_type": "grade",
        "task_uuid": bundle.task.uuid,
        "image_uuid": bundle.image_uuid,
        "disease": bundle.task.disease.name if bundle.task.disease else None,
        "grade_id": grade.id,
        "role_slot": grade.role_slot,
        "grade_name": grade.grade_name,
        "grade_description": grade.grade_description,
        "grader_user_id": grade.grader_user_id,
        "grader_username": grade.grader.username if grade.grader else None,
        "comment": grade.comment,
        "selected_features": json.loads(grade.selected_features_json) if grade.selected_features_json else None,
        "feature_geometry": grade.feature_geometry_json,
        "time_taken_seconds": grade.time_taken,
        "started_at": _iso(grade.start_time),
        "ai_model_name": grade.ai_model_name,
        "ai_model_version": grade.ai_model_version,
        "created_at": _iso(grade.created_at),
        "updated_at": _iso(grade.updated_at),
    }
    if with_annotations:
        record["annotation_set"] = serialize_annotation_set(annotation_set) if annotation_set else None
    else:
        record["annotation_set_updated_at"] = _iso(annotation_set.updated_at) if annotation_set else None
    return record


def _fingerprint(bundles: list[_TaskBundle], extra=None) -> str:
    """Change detector over tasks, grades, consensus and annotations.

    Any new/edited/removed grade or annotation instance changes it, so the
    client refreshes only the sidecar and never re-downloads the image.
    """
    parts = [extra]
    for bundle in bundles:
        task = bundle.task
        parts.append(
            [
                task.uuid,
                task.state,
                _iso(task.updated_at),
                _iso(bundle.consensus.decided_at) if bundle.consensus else None,
                bundle.consensus.final_grade_name if bundle.consensus else None,
                [
                    [
                        grade.id,
                        _iso(grade.updated_at),
                        _iso(getattr(grade, "_sync_annotation_set", None).updated_at)
                        if getattr(grade, "_sync_annotation_set", None) is not None
                        else None,
                        getattr(grade, "_sync_annotation_stats", None),
                    ]
                    for grade in bundle.grades
                ],
            ]
        )
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32]


def _coco_record(image_uuid: str, file_name: str, bundles: list[_TaskBundle], dims: tuple[int, int] | None) -> dict:
    """COCO block for one image built from every annotated grade on it."""
    width = height = None
    collected = []
    warnings = []
    for bundle in bundles:
        for grade in bundle.grades:
            annotation_set = getattr(grade, "_sync_annotation_set", None)
            if annotation_set is None:
                continue
            serialized = serialize_annotation_set(annotation_set)
            set_w = serialized.get("source_image_width") or (dims[0] if dims else None)
            set_h = serialized.get("source_image_height") or (dims[1] if dims else None)
            if not set_w or not set_h:
                warnings.append(f"grade {grade.id}: image dimensions unknown, skipped in COCO")
                continue
            if width is None:
                width, height = set_w, set_h
            elif (set_w, set_h) != (width, height):
                warnings.append(f"grade {grade.id}: annotation dimensions differ, skipped in COCO")
                continue
            for instance in serialized["instances"]:
                if instance["image_uuid"] != image_uuid or instance["geometry_type"] == "none":
                    continue
                collected.append((bundle, grade, instance))
    if width is None and dims:
        width, height = dims
    class_names = sorted({coco_class_name(instance) for _, _, instance in collected})
    category_ids = {name: index for index, name in enumerate(class_names, 1)}
    annotations = []
    for bundle, grade, instance in collected:
        try:
            converted = coco_annotation(instance, width, height)
        except (TypeError, ValueError, OSError):
            converted = None
        if converted is None:
            warnings.append(f"grade {grade.id}: invalid annotation geometry skipped in COCO")
            continue
        annotations.append(
            {
                "id": len(annotations) + 1,
                "image_id": 1,
                "category_id": category_ids[coco_class_name(instance)],
                "bbox": converted["bbox"],
                "area": converted["area"],
                "segmentation": converted["segmentation"],
                "iscrowd": 0,
                "instance_uuid": instance["uuid"],
                "source_task_uuid": bundle.task.uuid,
                "source_disease": bundle.task.disease.name if bundle.task.disease else None,
                "source_role_slot": grade.role_slot,
                "source_grader_user_id": grade.grader_user_id,
                "source_grade": grade.grade_name,
                "source_grade_id": grade.id,
                "source_grader_username": grade.grader.username if grade.grader else None,
                "source_graded_at": _iso(grade.updated_at or grade.created_at),
            }
        )
    return {
        "record_type": "coco",
        "image": {"id": 1, "file_name": file_name, "width": width, "height": height},
        "annotations": annotations,
        "categories": [{"id": category_ids[name], "name": name} for name in class_names],
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Encounter inventory
# ---------------------------------------------------------------------------


def _encounter_scope(ctx: SyncContext):
    return (
        PatientEncounters.project_id == ctx.project_id,
        PatientEncounters.lab_unit_id.in_(list(ctx.lab_unit_ids)),
    )


def _child_in_project(row, ctx: SyncContext) -> bool:
    return getattr(row, "project_id", None) in (None, ctx.project_id)


def _encounter_record(encounter: PatientEncounters, disease_names: dict, ctx: SyncContext) -> dict:
    pii = ctx.allows_pii(encounter.lab_unit_id)
    return {
        "record_type": "encounter",
        "uuid": encounter.uuid,
        "id": encounter.id,
        "lab_unit_id": encounter.lab_unit_id,
        "disease": disease_names.get(encounter.disease_id),
        "capture_date": _iso(encounter.capture_date_dt) or None,
        "is_set_based": encounter.is_set_based,
        "referral_suggestion": encounter.referral_suggestion,
        "referral_positive_diseases": encounter.referral_positive_diseases_json,
        "encounter_verified_status": encounter.encounter_verified_status,
        "dr_verified_status": encounter.dr_verified_status,
        "glaucoma_verified_status": encounter.glaucoma_verified_status,
        "identifiers_included": pii,
        "patient_id": encounter.patient_id if pii else None,
        "patient_name": encounter.name if pii else None,
        "remarks": encounter.remarks if pii else None,
        "metadata": encounter.metadata_json if pii else None,
    }


def _collect_encounter_media(db, ctx: SyncContext, encounters: list[PatientEncounters]):
    """Return {encounter_id: [(kind, row), ...]} honoring PII rules."""
    by_id = {e.id: e for e in encounters}
    ids = list(by_id)
    media: dict[int, list] = defaultdict(list)
    if not ids:
        return media
    files = db.execute(
        select(EncounterFile).where(EncounterFile.patient_encounter_id.in_(ids)).order_by(EncounterFile.id)
    ).scalars().all()
    set_images = db.execute(
        select(EncounterSetImage)
        .where(EncounterSetImage.patient_encounter_id.in_(ids))
        .order_by(EncounterSetImage.spatial_position, EncounterSetImage.id)
    ).scalars().all()
    pdfs = db.execute(
        select(EncounterFilePDF).where(EncounterFilePDF.patient_encounter_id.in_(ids)).order_by(EncounterFilePDF.id)
    ).scalars().all()
    detected = _pii_detected_uuids(db, [r.uuid for r in files] + [r.uuid for r in set_images])
    for row in files:
        lab = by_id[row.patient_encounter_id].lab_unit_id
        if not row.uuid or not _child_in_project(row, ctx):
            continue
        if row.uuid in detected and not ctx.allows_pii(lab):
            continue
        media[row.patient_encounter_id].append((KIND_ENCOUNTER_FILE, row))
    for row in set_images:
        lab = by_id[row.patient_encounter_id].lab_unit_id
        if not _child_in_project(row, ctx):
            continue
        if (row.is_pii or row.uuid in detected) and not ctx.allows_pii(lab):
            continue
        media[row.patient_encounter_id].append((KIND_ENCOUNTER_SET_IMAGE, row))
    for row in pdfs:
        lab = by_id[row.patient_encounter_id].lab_unit_id
        if row.uuid and _child_in_project(row, ctx) and ctx.allows_pii(lab):
            media[row.patient_encounter_id].append((KIND_ENCOUNTER_FILE_PDF, row))
    return media


def _media_item(kind: str, row, *, fingerprint: str | None) -> dict:
    if kind == KIND_ENCOUNTER_FILE:
        return {
            "uuid": row.uuid, "kind": kind, "ext": _ext(row.filename) or "jpg",
            "eye_side": row.eye_side, "centering": row.centering, "position": None,
            "is_pii": False, "has_edited": False, "source_md5": None,
            "created_at": None, "sidecar_fingerprint": fingerprint,
        }
    if kind == KIND_ENCOUNTER_SET_IMAGE:
        return {
            "uuid": row.uuid, "kind": kind, "ext": _ext(row.original_filename) or "jpg",
            "eye_side": None, "centering": None, "position": row.spatial_position,
            "is_pii": bool(row.is_pii), "has_edited": bool(row.edited_filename or row.s3_object_key_edited),
            "source_md5": row.file_hash, "created_at": _iso(row.created_at),
            "is_not_gradable": row.is_not_gradable, "sidecar_fingerprint": fingerprint,
        }
    if kind == KIND_ENCOUNTER_FILE_PDF:
        return {
            "uuid": row.uuid, "kind": kind, "ext": "pdf", "eye_side": row.eye_side,
            "centering": None, "position": None, "is_pii": True, "has_edited": False,
            "source_md5": None, "created_at": None, "sidecar_fingerprint": None,
        }
    return {
        "uuid": row.uuid, "kind": kind, "ext": _ext(row.filename) or "jpg",
        "eye_side": None, "centering": None, "position": None, "is_pii": False,
        "has_edited": bool(row.edited_filename or row.s3_object_key_edited),
        "source_md5": row.file_hash, "created_at": _iso(row.created_at),
        "lab_unit_id": row.lab_unit_id, "is_mydriatic": row.is_mydriatic,
        "sidecar_fingerprint": fingerprint,
    }


def list_encounters(db, ctx: SyncContext, *, after_id: int, limit: int) -> dict:
    encounters = db.execute(
        select(PatientEncounters)
        .where(*_encounter_scope(ctx), PatientEncounters.id > after_id)
        .order_by(PatientEncounters.id)
        .limit(limit)
    ).scalars().all()
    disease_names = dict(db.execute(select(Disease.id, Disease.name)).all())
    media = _collect_encounter_media(db, ctx, encounters)
    file_ids = [row.id for rows in media.values() for kind, row in rows if kind == KIND_ENCOUNTER_FILE]
    set_ids = [row.id for rows in media.values() for kind, row in rows if kind == KIND_ENCOUNTER_SET_IMAGE]
    bundles = _load_task_bundles(
        db, ctx, encounter_ids=[e.id for e in encounters], file_ids=file_ids,
        set_image_ids=set_ids, with_annotations=False,
    )
    by_encounter = defaultdict(list)
    by_image = defaultdict(list)
    for bundle in bundles:
        if bundle.encounter_id is not None:
            by_encounter[bundle.encounter_id].append(bundle)
        if bundle.image_uuid:
            by_image[bundle.image_uuid].append(bundle)
    items = []
    for encounter in encounters:
        record = _encounter_record(encounter, disease_names, ctx)
        images = [
            _media_item(kind, row, fingerprint=_fingerprint(by_image.get(row.uuid, []), extra=row.uuid))
            for kind, row in media.get(encounter.id, [])
        ]
        record.pop("record_type")
        record["images"] = images
        record["sidecar_fingerprint"] = _fingerprint(
            by_encounter.get(encounter.id, []), extra=[record.get("capture_date"), record.get("encounter_verified_status"), len(images)]
        )
        items.append(record)
    next_after = encounters[-1].id if len(encounters) == limit else None
    return {"items": items, "next_after_id": next_after}


def list_direct_images(db, ctx: SyncContext, *, after_id: int, limit: int) -> dict:
    rows = db.execute(
        select(DirectImageUpload)
        .where(
            DirectImageUpload.project_id == ctx.project_id,
            DirectImageUpload.lab_unit_id.in_(list(ctx.lab_unit_ids)),
            DirectImageUpload.id > after_id,
        )
        .order_by(DirectImageUpload.id)
        .limit(limit)
    ).scalars().all()
    detected = _pii_detected_uuids(db, [r.uuid for r in rows])
    visible = [r for r in rows if r.uuid not in detected or ctx.allows_pii(r.lab_unit_id)]
    bundles = _load_task_bundles(db, ctx, direct_ids=[r.id for r in visible], with_annotations=False)
    by_image = defaultdict(list)
    for bundle in bundles:
        by_image[bundle.image_uuid].append(bundle)
    items = [
        _media_item(KIND_DIRECT_IMAGE, row, fingerprint=_fingerprint(by_image.get(row.uuid, []), extra=row.uuid))
        for row in visible
    ]
    next_after = rows[-1].id if len(rows) == limit else None
    return {"items": items, "next_after_id": next_after}


# ---------------------------------------------------------------------------
# Sidecars
# ---------------------------------------------------------------------------


def _validate_uuid_batch(values, name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise ProjectSyncValidationError(f"{name} must be a list of UUID strings.")
    cleaned = list(dict.fromkeys(v.strip() for v in values if v and v.strip()))
    if len(cleaned) > MAX_SIDECAR_BATCH:
        raise ProjectSyncValidationError(f"At most {MAX_SIDECAR_BATCH} {name} per request.")
    if any(len(v) > 36 for v in cleaned):
        raise ProjectSyncValidationError(f"{name} contains an invalid UUID.")
    return cleaned


def build_sidecars(db, ctx: SyncContext, *, encounter_uuids, image_uuids) -> dict:
    """Return JSONL-ready record lists keyed by encounter / image UUID.

    Unknown or out-of-scope UUIDs are listed under ``missing`` rather than
    raising, so one stale entry never blocks a batch.
    """
    encounter_uuids = _validate_uuid_batch(encounter_uuids, "encounters")
    image_uuids = _validate_uuid_batch(image_uuids, "images")
    result = {"encounters": {}, "images": {}, "missing": []}
    disease_names = dict(db.execute(select(Disease.id, Disease.name)).all())

    if encounter_uuids:
        encounters = db.execute(
            select(PatientEncounters).where(*_encounter_scope(ctx), PatientEncounters.uuid.in_(encounter_uuids))
        ).scalars().all()
        found = {e.uuid for e in encounters}
        result["missing"].extend(u for u in encounter_uuids if u not in found)
        media = _collect_encounter_media(db, ctx, encounters)
        file_ids = [row.id for rows in media.values() for kind, row in rows if kind == KIND_ENCOUNTER_FILE]
        set_ids = [row.id for rows in media.values() for kind, row in rows if kind == KIND_ENCOUNTER_SET_IMAGE]
        bundles = _load_task_bundles(
            db, ctx, encounter_ids=[e.id for e in encounters], file_ids=file_ids,
            set_image_ids=set_ids, with_annotations=False,
        )
        by_encounter = defaultdict(list)
        for bundle in bundles:
            by_encounter[bundle.encounter_id].append(bundle)
        for encounter in encounters:
            records = [{"schema": SIDECAR_SCHEMA, **_encounter_record(encounter, disease_names, ctx)}]
            for kind, row in media.get(encounter.id, []):
                records.append({"record_type": "image", **_media_item(kind, row, fingerprint=None)})
            for bundle in by_encounter.get(encounter.id, []):
                records.append(_task_record(bundle))
                records.extend(_grade_record(bundle, grade, with_annotations=False) for grade in bundle.grades)
            result["encounters"][encounter.uuid] = records

    if image_uuids:
        for image_uuid in image_uuids:
            try:
                resource = authorize_sync_media(db, ctx, image_uuid)
            except ProjectSyncNotFound:
                result["missing"].append(image_uuid)
                continue
            if resource.source_type == MediaSourceType.ENCOUNTER_FILE_PDF:
                result["missing"].append(image_uuid)
                continue
            result["images"][image_uuid] = _image_sidecar(db, ctx, resource)
    return result


def _image_sidecar(db, ctx: SyncContext, resource: AuthorizedMediaSource) -> list[dict]:
    kind_map = {
        MediaSourceType.ENCOUNTER_FILE: (KIND_ENCOUNTER_FILE, EncounterFile, "file_ids"),
        MediaSourceType.ENCOUNTER_SET_IMAGE: (KIND_ENCOUNTER_SET_IMAGE, EncounterSetImage, "set_image_ids"),
        MediaSourceType.DIRECT_IMAGE_UPLOAD: (KIND_DIRECT_IMAGE, DirectImageUpload, "direct_ids"),
    }
    kind, model, arg = kind_map[resource.source_type]
    row = db.get(model, resource.source_id)
    bundles = _load_task_bundles(db, ctx, with_annotations=True, **{arg: [row.id]})
    encounter_uuid = None
    if resource.patient_encounter_id:
        encounter_uuid = db.execute(
            select(PatientEncounters.uuid).where(PatientEncounters.id == resource.patient_encounter_id)
        ).scalar_one_or_none()
    dims = db.execute(
        select(ImageMetadata.width, ImageMetadata.height).where(
            ImageMetadata.image_uuid == row.uuid, ImageMetadata.image_variant == "orig"
        ).limit(1)
    ).first()
    item = _media_item(kind, row, fingerprint=None)
    file_name = f"{row.uuid}.{item['ext']}"
    records = [
        {
            "schema": SIDECAR_SCHEMA,
            "record_type": "image",
            **item,
            "encounter_uuid": encounter_uuid,
            "lab_unit_id": resource.lab_unit_id,
            "file_name": file_name,
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
        }
    ]
    for bundle in bundles:
        records.append(_task_record(bundle))
        records.extend(_grade_record(bundle, grade, with_annotations=True) for grade in bundle.grades)
    records.append(_coco_record(row.uuid, file_name, bundles, (dims[0], dims[1]) if dims and dims[0] and dims[1] else None))
    return records


# ---------------------------------------------------------------------------
# Per-object authorization for downloads
# ---------------------------------------------------------------------------


def authorize_sync_media(db, ctx: SyncContext, media_uuid: str) -> AuthorizedMediaSource:
    """Resolve one UUID and prove it sits inside the grant's current scope."""
    media_uuid = (media_uuid or "").strip()
    if not media_uuid or len(media_uuid) > 36:
        raise ProjectSyncNotFound("Media not found.")
    try:
        resource = resolve_media_source(db, media_uuid=media_uuid, expected_sources=SYNC_MEDIA_SOURCES)
        resource.record_scope()
    except MediaResolutionError as exc:
        raise ProjectSyncNotFound("Media not found.") from exc
    if resource.project_id != ctx.project_id or not ctx.allows_lab(resource.lab_unit_id):
        raise ProjectSyncNotFound("Media not found.")
    if ctx.allows_pii(resource.lab_unit_id):
        return resource
    if resource.source_type == MediaSourceType.ENCOUNTER_FILE_PDF:
        raise ProjectSyncNotFound("Media not found.")
    if resource.source_type == MediaSourceType.ENCOUNTER_SET_IMAGE:
        row = db.get(EncounterSetImage, resource.source_id)
        if row is None or row.is_pii:
            raise ProjectSyncNotFound("Media not found.")
    if resource.uuid in _pii_detected_uuids(db, [resource.uuid]):
        raise ProjectSyncNotFound("Media not found.")
    return resource
