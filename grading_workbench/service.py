from collections.abc import Callable
from hashlib import sha256

from sqlalchemy.orm import selectinload

from models import GradingTask
from utils.dualGradingEligibility import get_user_eligibility_for_task

from .contracts import (
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
    raise WorkbenchImageUnavailable("The grading target does not have a viewable image.")


def _context_revision(task: GradingTask, slot: str, image_uuid: str) -> str:
    updated_at = task.updated_at.isoformat() if task.updated_at is not None else ""
    value = "\x1f".join((task.uuid, task.state, updated_at, slot, image_uuid))
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
        )
        .filter(GradingTask.uuid == normalized_uuid)
        .first()
    )
    if task is None:
        raise WorkbenchTargetNotFound("Grading task not found.")

    if not get_user_eligibility_for_task(db, user_id, task.id, normalized_slot):
        raise WorkbenchAccessDenied("You are not eligible to view this grading slot.")

    image, image_source = _resolve_image(task)
    image_uuid = str(image.uuid)
    filename = getattr(image, "filename", None) or getattr(image, "original_filename", None)

    return WorkspaceDTO(
        schema_version=1,
        context_revision=_context_revision(task, normalized_slot, image_uuid),
        target=TargetDTO(type="task", ref=task.uuid, slot=normalized_slot),
        task=TaskDTO(
            uuid=task.uuid,
            state=task.state,
            disease=NamedEntityDTO(id=task.disease.id, name=task.disease.name),
            lab_unit=NamedEntityDTO(id=task.lab_unit.id, name=task.lab_unit.name),
        ),
        image=ImageDTO(
            uuid=image_uuid,
            source=image_source,
            url=image_url_builder(image_uuid),
            filename=filename,
        ),
        capabilities=WorkspaceCapabilitiesDTO(),
        read_only_reasons=("Grading submission is not enabled in this foundation release.",),
    )
