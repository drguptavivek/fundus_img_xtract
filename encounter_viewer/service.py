"""Build authorized, normalized viewer DTOs without exposing PII."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from flask import url_for
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from grading.workbench.models import AnnotationSet
from media.authorization import (
    IMAGE_SOURCE_TYPES,
    MediaAccessDenied,
    MediaResolutionError,
    authorize_media_source,
)
from models import (
    AIInferenceRun,
    Consensus,
    DirectImageUpload,
    EncounterFile,
    EncounterSetImage,
    Grade,
    GradingTask,
    ImageMetadata,
    LabUnit,
    PatientEncounters,
)

from .contracts import (
    EncounterViewerDTO,
    ViewerActionDTO,
    ViewerAnnotationDTO,
    ViewerGradeDTO,
    ViewerImageDTO,
    ViewerInferenceDTO,
    ViewerTargetDTO,
)
from .policy import can_access_encounter, can_verify_encounter, can_view_results


class ViewerNotFound(LookupError):
    pass


class ViewerAccessDenied(PermissionError):
    pass


def build_encounter_viewer(db: Session, *, user, encounter_id: int) -> EncounterViewerDTO:
    encounter = (
        db.query(PatientEncounters)
        .options(
            joinedload(PatientEncounters.project),
            joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            selectinload(PatientEncounters.encounter_files).selectinload(EncounterFile.camera),
            selectinload(PatientEncounters.encounter_set_images).selectinload(EncounterSetImage.camera),
        )
        .filter(PatientEncounters.id == encounter_id)
        .first()
    )
    if encounter is None:
        raise ViewerNotFound("Viewer resource not found")
    if not can_access_encounter(db, user=user, encounter=encounter):
        raise ViewerAccessDenied("Viewer resource not found")

    hospital_id = encounter.lab_unit.hospital_id if encounter.lab_unit else None
    show_results = can_view_results(
        db,
        user=user,
        encounter=encounter,
        project_id=encounter.project_id,
        hospital_id=hospital_id,
        lab_unit_id=encounter.lab_unit_id,
    )
    source_rows: list[tuple[str, Any]] = [
        ("encounter_file", row)
        for row in encounter.encounter_files
        if row.uuid
    ]
    source_rows.extend(
        ("encounter_set_image", row)
        for row in encounter.encounter_set_images
        if row.uuid and not row.is_pii
    )
    source_rows.sort(key=lambda item: (
        getattr(item[1], "spatial_position", None) is None,
        getattr(item[1], "spatial_position", 0) or 0,
        item[1].id,
    ))
    images, image_ids = _authorized_images(db, user=user, source_rows=source_rows)
    task_map, encounter_targets, inferences = _clinical_evidence(
        db,
        encounter=encounter,
        image_ids=image_ids,
        show_results=show_results,
    )
    images = tuple(
        ViewerImageDTO(**{**image.__dict__, "targets": task_map.get((image.source_type, image.source_id), ())})
        for image in images
    )
    camera_names = sorted({image.camera for image in images if image.camera})
    actions: list[ViewerActionDTO] = []
    if can_verify_encounter(db, user=user, encounter=encounter):
        actions.append(ViewerActionDTO(
            kind="verify",
            label="View Verification" if encounter.encounter_verified_status == "verified" else "Verify",
            url=url_for("verify_encounter_set.verify_encounter", uuid=encounter.uuid),
        ))
    capture_date = encounter.capture_date_dt.isoformat() if encounter.capture_date_dt else encounter.capture_date
    return EncounterViewerDTO(
        resource_kind="encounter",
        resource_id=str(encounter.id),
        source_kind="encounter_set" if encounter.is_set_based else "legacy_encounter",
        capture_date=capture_date,
        project_code=encounter.project.code if encounter.project else None,
        hospital=encounter.lab_unit.hospital.name if encounter.lab_unit and encounter.lab_unit.hospital else None,
        lab_unit=encounter.lab_unit.name if encounter.lab_unit else None,
        verified_status=encounter.encounter_verified_status,
        can_view_clinical_results=show_results,
        images=images,
        encounter_targets=encounter_targets,
        inferences=inferences,
        actions=tuple(actions),
        metadata={
            "source": "EncounterSet" if encounter.is_set_based else "Legacy encounter",
            "image_count": len(images),
            "cameras": ", ".join(camera_names) if camera_names else "Unavailable",
        },
    )


def build_image_viewer(db: Session, *, user, image_uuid: str) -> EncounterViewerDTO:
    try:
        resource = authorize_media_source(
            db,
            user=user,
            media_uuid=image_uuid,
            action="media.image.view",
            expected_sources=IMAGE_SOURCE_TYPES,
        )
    except MediaResolutionError as exc:
        raise ViewerNotFound("Viewer resource not found") from exc
    except MediaAccessDenied as exc:
        raise ViewerAccessDenied("Viewer resource not found") from exc
    if resource.patient_encounter_id is not None:
        return build_encounter_viewer(db, user=user, encounter_id=resource.patient_encounter_id)
    upload = (
        db.query(DirectImageUpload)
        .options(
            joinedload(DirectImageUpload.project),
            joinedload(DirectImageUpload.hospital),
            joinedload(DirectImageUpload.lab_unit),
            joinedload(DirectImageUpload.camera),
        )
        .filter(DirectImageUpload.id == resource.source_id)
        .first()
    )
    if upload is None:
        raise ViewerNotFound("Viewer resource not found")
    show_results = can_view_results(
        db,
        user=user,
        encounter=None,
        project_id=upload.project_id,
        hospital_id=upload.hospital_id,
        lab_unit_id=upload.lab_unit_id,
    )
    images, image_ids = _authorized_images(
        db,
        user=user,
        source_rows=[("direct_image_upload", upload)],
    )
    task_map, encounter_targets, inferences = _direct_clinical_evidence(
        db, upload=upload, show_results=show_results
    )
    images = tuple(
        ViewerImageDTO(**{**image.__dict__, "targets": task_map.get((image.source_type, image.source_id), ())})
        for image in images
    )
    return EncounterViewerDTO(
        resource_kind="image",
        resource_id=upload.uuid,
        source_kind="direct_image_upload",
        capture_date=upload.created_at.date().isoformat() if upload.created_at else None,
        project_code=upload.project.code if upload.project else None,
        hospital=upload.hospital.name if upload.hospital else None,
        lab_unit=upload.lab_unit.name if upload.lab_unit else None,
        verified_status=upload.verifications[-1].verified_status if upload.verifications else None,
        can_view_clinical_results=show_results,
        images=images,
        encounter_targets=encounter_targets,
        inferences=inferences,
        metadata={"source": "Direct image", "image_count": len(images)},
    )


def _authorized_images(db: Session, *, user, source_rows: list[tuple[str, Any]]):
    uuids = [row.uuid for _, row in source_rows]
    metadata_by_uuid = {
        row.image_uuid: row
        for row in db.query(ImageMetadata)
        .filter(ImageMetadata.image_uuid.in_(uuids), ImageMetadata.image_variant == "orig")
        .all()
    } if uuids else {}
    images: list[ViewerImageDTO] = []
    image_ids: dict[str, list[int]] = defaultdict(list)
    for index, (source_type, row) in enumerate(source_rows, start=1):
        try:
            authorize_media_source(
                db,
                user=user,
                media_uuid=row.uuid,
                action="media.image.view",
                expected_sources=IMAGE_SOURCE_TYPES,
            )
        except (MediaAccessDenied, MediaResolutionError):
            continue
        meta = metadata_by_uuid.get(row.uuid)
        raw = row.metadata_json if source_type == "encounter_set_image" and isinstance(row.metadata_json, dict) else {}
        laterality = _laterality(
            raw.get("laterality") or raw.get("eye") or getattr(row, "eye_side", None)
        )
        focus = raw.get("focus") or raw.get("fundus_field") or raw.get("field") or getattr(row, "centering", None)
        position = getattr(row, "spatial_position", None) or index
        camera = row.camera.name if getattr(row, "camera", None) else None
        safe_metadata = _safe_image_metadata(raw, meta)
        images.append(ViewerImageDTO(
            source_type=source_type,
            source_id=row.id,
            uuid=row.uuid,
            position=position,
            laterality=laterality,
            focus=str(focus) if focus not in (None, "") else None,
            camera=camera,
            media_url=url_for("media._imgForGradingByUUID", uuid_str=row.uuid),
            thumbnail_url=url_for("media._universalImageThumbnailByUUID", uuid_str=row.uuid),
            metadata=safe_metadata,
        ))
        image_ids[source_type].append(row.id)
    return tuple(images), image_ids


def _safe_image_metadata(raw: dict[str, Any], meta: ImageMetadata | None) -> dict[str, Any]:
    allowed = {
        "image_variant": "Variant",
        "image_segment": "Segment",
        "quality": "Quality",
        "is_montage": "Montage",
        "is_cropped": "Cropped",
        "is_mydriatic": "Mydriatic",
    }
    values = {label: raw.get(key) for key, label in allowed.items() if raw.get(key) not in (None, "")}
    if meta:
        if meta.width and meta.height:
            values["Dimensions"] = f"{meta.width} × {meta.height}"
        if meta.format:
            values["Format"] = meta.format
        if meta.mode:
            values["Colour mode"] = meta.mode
    return values


def _clinical_evidence(db: Session, *, encounter, image_ids, show_results):
    if not show_results:
        return {}, (), ()
    clauses = [GradingTask.patient_encounter_id == encounter.id]
    if image_ids.get("encounter_file"):
        clauses.append(GradingTask.encounter_file_id.in_(image_ids["encounter_file"]))
    if image_ids.get("encounter_set_image"):
        clauses.append(GradingTask.encounter_set_image_id.in_(image_ids["encounter_set_image"]))
    tasks = _load_tasks(db, or_(*clauses))
    return _evidence_from_tasks(db, tasks, encounter=encounter)


def _direct_clinical_evidence(db: Session, *, upload, show_results):
    if not show_results:
        return {}, (), ()
    tasks = _load_tasks(db, GradingTask.direct_image_upload_id == upload.id)
    return _evidence_from_tasks(db, tasks, encounter=None)


def _load_tasks(db: Session, criterion):
    return (
        db.query(GradingTask)
        .options(
            joinedload(GradingTask.disease),
            selectinload(GradingTask.grades).selectinload(Grade.label),
            joinedload(GradingTask.consensus).joinedload(Consensus.final_label),
            selectinload(GradingTask.inference_runs).joinedload(AIInferenceRun.ai_model),
        )
        .filter(criterion)
        .order_by(GradingTask.disease_id, GradingTask.id)
        .all()
    )


def _evidence_from_tasks(db: Session, tasks: list[GradingTask], *, encounter):
    grade_ids = [grade.id for task in tasks for grade in task.grades]
    annotations_by_grade: dict[int, tuple[ViewerAnnotationDTO, ...]] = {}
    if grade_ids:
        sets = db.query(AnnotationSet).filter(AnnotationSet.grade_id.in_(grade_ids)).all()
        for annotation_set in sets:
            annotations_by_grade[annotation_set.grade_id] = tuple(
                ViewerAnnotationDTO(
                    label=item.class_label_snapshot,
                    geometry_type=item.geometry_type,
                    geometry=item.geometry_json,
                )
                for item in annotation_set.instances
            )
    image_targets: dict[tuple[str, int], list[ViewerTargetDTO]] = defaultdict(list)
    encounter_targets: list[ViewerTargetDTO] = []
    inferences: list[ViewerInferenceDTO] = []
    for task in tasks:
        grades = tuple(
            ViewerGradeDTO(
                role_slot=grade.role_slot,
                label=grade.grade_name or (grade.label.impression if grade.label else "Unknown"),
                model=(f"{grade.ai_model_name or ''} {grade.ai_model_version or ''}".strip() or None),
                review_status=grade.ai_review_status,
            )
            for grade in sorted(task.grades, key=lambda item: (item.role_slot, item.id))
        )
        annotations = tuple(
            annotation
            for grade in task.grades
            for annotation in annotations_by_grade.get(grade.id, ())
        )
        target = ViewerTargetDTO(
            task_uuid=task.uuid,
            disease=task.disease.name if task.disease else task.grades[0].disease_name if task.grades else "Unknown",
            target_level=task.grading_target_level or ("encounter" if task.patient_encounter_id else "image"),
            state=task.state,
            final_label=(
                task.consensus.final_grade_name
                or (task.consensus.final_label.impression if task.consensus.final_label else None)
            ) if task.consensus else None,
            final_method=task.consensus.method if task.consensus else None,
            grades=grades,
            annotations=annotations,
        )
        if task.encounter_file_id:
            image_targets[("encounter_file", task.encounter_file_id)].append(target)
        elif task.encounter_set_image_id:
            image_targets[("encounter_set_image", task.encounter_set_image_id)].append(target)
        elif task.direct_image_upload_id:
            image_targets[("direct_image_upload", task.direct_image_upload_id)].append(target)
        else:
            encounter_targets.append(target)
        for run in task.inference_runs:
            model = f"{run.ai_model.name} {run.ai_model.version}" if run.ai_model else None
            inferences.append(ViewerInferenceDTO(
                provider="WAI" if run.integration and run.integration.provider == "wadhwani_glaucoma" else "AI",
                disease=target.disease,
                result=next((g.label for g in grades if g.role_slot == "ai"), None),
                status=run.status,
                model=model,
            ))
    if encounter is not None:
        inferences.extend(_report_inferences(encounter))
    return (
        {key: tuple(value) for key, value in image_targets.items()},
        tuple(encounter_targets),
        tuple(inferences),
    )


def _report_inferences(encounter: PatientEncounters) -> tuple[ViewerInferenceDTO, ...]:
    rows: list[ViewerInferenceDTO] = []
    for report in encounter.dr_reports:
        rows.append(ViewerInferenceDTO(provider="Remidio", disease="DR", result=report.result))
    for report in encounter.amd_reports:
        rows.append(ViewerInferenceDTO(provider="Remidio", disease="AMD", result=report.result))
    for report in encounter.glaucoma_results_cleaned:
        rows.append(ViewerInferenceDTO(
            provider="Remidio",
            disease="Glaucoma",
            result=report.result,
            metrics={"vCDR OD": report.vcdr_right_num, "vCDR OS": report.vcdr_left_num},
        ))
    return tuple(rows)


def _laterality(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"OD", "RIGHT", "R", "RE"}:
        return "OD"
    if normalized in {"OS", "LEFT", "L", "LE"}:
        return "OS"
    if normalized in {"OU", "BOTH", "BILATERAL"}:
        return "OU"
    return "OU"
