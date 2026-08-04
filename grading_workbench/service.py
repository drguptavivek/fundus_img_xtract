from collections.abc import Callable
from hashlib import sha256
import json

from sqlalchemy.orm import selectinload

from models import EncounterFile, EncounterSetImage, GradingTask, PatientEncounters
from project_annotations.contracts import AnnotationContextDTO
from project_annotations.service import resolve_task_annotation_context
from utils.dualGradingEligibility import get_user_eligibility_for_task
from utils.linkedGradingUtils import get_linked_disease_ids, get_primary_disease_id
from utils.masterUtils import fetch_active_disease_gradings

from .contracts import (
    ExistingGradeDTO,
    GradingFeatureDTO,
    GradingOptionDTO,
    GradingPanelDTO,
    ImageDTO,
    NamedEntityDTO,
    TargetDTO,
    TaskDTO,
    WorkspaceCapabilitiesDTO,
    WorkspaceDTO,
)
from .errors import (
    InvalidWorkbenchTarget,
    WorkbenchAccessDenied,
    WorkbenchImageUnavailable,
    WorkbenchTargetNotFound,
)


SUPPORTED_SLOTS = frozenset({"resident", "resident2", "arbitrator"})


def _resolve_image(task: GradingTask) -> tuple[object, str]:
    if task.encounter_file is not None:
        return task.encounter_file, "encounter_file"
    if task.direct_image is not None:
        return task.direct_image, "direct_image"
    if task.encounter_set_image is not None:
        return task.encounter_set_image, "encounter_set_image"
    if task.patient_encounter is not None:
        visible_set_image = next(
            (
                image
                for image in sorted(
                    task.patient_encounter.encounter_set_images,
                    key=lambda item: (item.spatial_position, item.id),
                )
                if image.visible_to_grader
            ),
            None,
        )
        if visible_set_image is not None:
            return visible_set_image, "encounter_set_image"
        encounter_image = next(
            (
                image
                for image in sorted(task.patient_encounter.encounter_files, key=lambda item: item.id)
                if image.file_type == "image"
            ),
            None,
        )
        if encounter_image is not None:
            return encounter_image, "encounter_file"
    raise WorkbenchImageUnavailable("The grading target does not have a viewable image.")


def _image_dto(image: object, source: str, image_url_builder: Callable[[str], str]) -> ImageDTO:
    image_uuid = str(image.uuid)
    return ImageDTO(
        uuid=image_uuid,
        source=source,
        url=image_url_builder(image_uuid),
        filename=getattr(image, "filename", None) or getattr(image, "original_filename", None),
        position=getattr(image, "spatial_position", None),
    )


def _workspace_images(
    db,
    task: GradingTask,
    image_url_builder: Callable[[str], str],
) -> tuple[ImageDTO, ...]:
    encounter_id = task.patient_encounter_id
    if encounter_id is None and task.encounter_set_image is not None:
        encounter_id = task.encounter_set_image.patient_encounter_id
    if encounter_id is None and task.encounter_file is not None:
        encounter_id = task.encounter_file.patient_encounter_id

    if task.encounter_set_package_id is not None or task.patient_encounter_id is not None:
        set_images = (
            db.query(EncounterSetImage)
            .filter(
                EncounterSetImage.patient_encounter_id == encounter_id,
                EncounterSetImage.visible_to_grader.is_(True),
            )
            .order_by(EncounterSetImage.spatial_position, EncounterSetImage.id)
            .all()
        )
        if set_images:
            return tuple(
                _image_dto(image, "encounter_set_image", image_url_builder)
                for image in set_images
            )
        encounter_images = (
            db.query(EncounterFile)
            .filter(
                EncounterFile.patient_encounter_id == encounter_id,
                EncounterFile.file_type == "image",
            )
            .order_by(EncounterFile.id)
            .all()
        )
        if encounter_images:
            return tuple(
                _image_dto(image, "encounter_file", image_url_builder)
                for image in encounter_images
            )

    image, source = _resolve_image(task)
    return (_image_dto(image, source, image_url_builder),)


def _same_target_filters(task: GradingTask) -> list:
    if task.encounter_file_id is not None:
        return [GradingTask.encounter_file_id == task.encounter_file_id]
    if task.direct_image_upload_id is not None:
        return [GradingTask.direct_image_upload_id == task.direct_image_upload_id]
    if task.encounter_set_image_id is not None:
        return [GradingTask.encounter_set_image_id == task.encounter_set_image_id]
    if task.patient_encounter_id is not None:
        return [GradingTask.patient_encounter_id == task.patient_encounter_id]
    return [GradingTask.id == task.id]


def _related_panel_tasks(db, task: GradingTask) -> list[GradingTask]:
    query = db.query(GradingTask).options(
        selectinload(GradingTask.disease),
        selectinload(GradingTask.grades),
    )
    if task.encounter_set_package_id is not None:
        rows = query.filter(
            GradingTask.encounter_set_package_id == task.encounter_set_package_id
        ).all()
        return sorted(
            rows,
            key=lambda item: (
                0 if (item.grading_target_level or item.disease.grading_scope) == "image" else 1,
                item.disease.name.casefold(),
                item.id,
            ),
        )

    primary_id = get_primary_disease_id(db, task.disease_id)
    disease_ids = [primary_id, *get_linked_disease_ids(db, primary_id)]
    if len(disease_ids) == 1:
        return [task]
    rows = query.filter(
        *_same_target_filters(task),
        GradingTask.disease_id.in_(disease_ids),
    ).all()
    order = {disease_id: index for index, disease_id in enumerate(disease_ids)}
    return sorted(rows, key=lambda item: (order.get(item.disease_id, len(order)), item.id))


def _selected_feature_ids(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return ()
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return ()
    selected: list[int] = []
    for value in values if isinstance(values, list) else []:
        feature_id = value.get("id") if isinstance(value, dict) else value
        if isinstance(feature_id, int) and feature_id not in selected:
            selected.append(feature_id)
    return tuple(selected)


def _legacy_annotations(payload: dict | None) -> tuple[dict, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return ()
    return tuple(item for item in payload["items"] if isinstance(item, dict))


def _panel_read_only(task: GradingTask, *, db, user_id: int, slot: str) -> tuple[bool, str | None]:
    if not get_user_eligibility_for_task(db, user_id, task.id, slot):
        return True, "You are not eligible to grade this panel."
    if slot == "arbitrator" and task.state not in {"arbitration", "final"}:
        return True, f"This panel is not awaiting arbitration ({task.state})."
    if task.state == "final" and slot != "arbitrator":
        return True, "This panel is final and available for clinical context only."
    return False, None


def _grading_panel(db, task: GradingTask, *, user_id: int, slot: str) -> GradingPanelDTO:
    read_only, read_only_reason = _panel_read_only(task, db=db, user_id=user_id, slot=slot)
    grades = fetch_active_disease_gradings(db, task.disease_id)
    existing = next(
        (
            grade
            for grade in task.grades
            if grade.grader_user_id == user_id and grade.role_slot == slot
        ),
        None,
    )
    existing_dto = None
    if existing is not None:
        existing_dto = ExistingGradeDTO(
            id=existing.id,
            grading_id=existing.disease_grading_id,
            selected_feature_ids=_selected_feature_ids(existing.selected_features_json),
            comment=existing.comment or "",
            annotations=_legacy_annotations(existing.feature_geometry_json),
        )
    target_level = task.grading_target_level or task.disease.grading_scope or "image"
    return GradingPanelDTO(
        id=f"task:{task.uuid}",
        task_uuid=task.uuid,
        disease=NamedEntityDTO(id=task.disease.id, name=task.disease.name),
        grading_scope=target_level,
        target_level=target_level,
        state=task.state,
        read_only=read_only,
        read_only_reason=read_only_reason,
        grades=tuple(
            GradingOptionDTO(
                id=grade.id,
                impression=grade.impression,
                display_order=grade.display_order,
                is_active=bool(grade.is_active),
                is_ungradable=bool(grade.is_ungradable),
                guidelines=grade.guidelines,
                features=tuple(
                    GradingFeatureDTO(
                        id=feature.id,
                        sr_no=feature.sr_no,
                        label=feature.label,
                    )
                    for feature in sorted(
                        grade.features or [],
                        key=lambda item: (item.sr_no, item.id),
                    )
                ),
            )
            for grade in grades
        ),
        existing_grade=existing_dto,
    )


def _context_revision(
    task: GradingTask,
    slot: str,
    image_uuid: str,
    annotation_context: AnnotationContextDTO,
) -> str:
    updated_at = task.updated_at.isoformat() if task.updated_at is not None else ""
    value = "\x1f".join(
        (
            task.uuid,
            task.state,
            updated_at,
            slot,
            image_uuid,
            annotation_context.policy_source,
            str(annotation_context.project_id or ""),
            str(annotation_context.revision),
        )
    )
    return sha256(value.encode("utf-8")).hexdigest()


def resolve_task_workspace(
    db,
    *,
    user_id: int,
    task_uuid: str,
    slot: str,
    image_url_builder: Callable[[str], str],
) -> WorkspaceDTO:
    normalized_uuid = (task_uuid or "").strip()
    normalized_slot = (slot or "").strip().lower()
    if not normalized_uuid:
        raise InvalidWorkbenchTarget("A task reference is required.")
    if normalized_slot not in SUPPORTED_SLOTS:
        raise InvalidWorkbenchTarget("Unsupported grading slot.")

    task = (
        db.query(GradingTask)
        .options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.lab_unit),
            selectinload(GradingTask.encounter_file),
            selectinload(GradingTask.direct_image),
            selectinload(GradingTask.encounter_set_image),
            selectinload(GradingTask.patient_encounter).selectinload(PatientEncounters.encounter_set_images),
            selectinload(GradingTask.patient_encounter).selectinload(PatientEncounters.encounter_files),
            selectinload(GradingTask.grades),
        )
        .filter(GradingTask.uuid == normalized_uuid)
        .first()
    )
    if task is None:
        raise WorkbenchTargetNotFound("Grading task not found.")

    if not get_user_eligibility_for_task(db, user_id, task.id, normalized_slot):
        raise WorkbenchAccessDenied("You are not eligible to view this grading slot.")

    images = _workspace_images(db, task, image_url_builder)
    primary_image = next(
        (
            image
            for image in images
            if task.encounter_set_image is not None
            and image.uuid == str(task.encounter_set_image.uuid)
        ),
        images[0],
    )
    image_uuid = primary_image.uuid
    annotation_context = resolve_task_annotation_context(db, task)
    panels = tuple(
        _grading_panel(db, panel_task, user_id=user_id, slot=normalized_slot)
        for panel_task in _related_panel_tasks(db, task)
    )

    return WorkspaceDTO(
        schema_version=2,
        context_revision=_context_revision(
            task,
            normalized_slot,
            image_uuid,
            annotation_context,
        ),
        target=TargetDTO(type="task", ref=task.uuid, slot=normalized_slot),
        task=TaskDTO(
            uuid=task.uuid,
            state=task.state,
            disease=NamedEntityDTO(id=task.disease.id, name=task.disease.name),
            lab_unit=NamedEntityDTO(id=task.lab_unit.id, name=task.lab_unit.name),
        ),
        image=primary_image,
        images=images,
        active_image_uuid=image_uuid,
        panels=panels,
        annotation_context=annotation_context,
        capabilities=WorkspaceCapabilitiesDTO(annotate=annotation_context.enabled),
        read_only_reasons=("Grading submission is not enabled in this foundation release.",),
    )
