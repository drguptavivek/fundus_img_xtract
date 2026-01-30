from sqlalchemy import select, exists, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, Session as OrmSession
from typing import Optional, Tuple

from db_transaction_manager import transaction_scope
from models import (
    GradingTask, Grade, Consensus, DirectImageUpload, DirectImageVerify,
    EncounterFile, PatientEncounters, Disease, DiseaseGrading, LabUnit
)
from utils.linkedGradingUtils import get_linked_disease_ids, get_primary_disease_id


def _resolve_image_by_uuid(db, image_uuid: str) -> Tuple[str, int, int]:
    """
    Return a tuple (kind, image_id, lab_unit_id) where kind in {'direct','encounter'}.
    Raises ValueError if not found.
    """
    diu = db.execute(select(DirectImageUpload).where(DirectImageUpload.uuid == image_uuid)).scalar_one_or_none()
    if diu:
        return ('direct', diu.id, diu.lab_unit_id)
    ef = db.execute(select(EncounterFile).where(EncounterFile.uuid == image_uuid)).scalar_one_or_none()
    if ef:
        return ('encounter', ef.id, ef.lab_unit_id)
    raise ValueError('Image not found')


def _is_verified_for_disease(db, kind: str, image_id: int, disease_id: int) -> bool:
    """
    Disease-specific verification gating.
    - direct: requires DirectImageVerify.verified_status == 'verified'
    - encounter (DR): PatientEncounters.dr_verified_status == 'verified'
    - encounter (Glaucoma): PatientEncounters.glaucoma_verified_status == 'verified'
    Other diseases: return False until policy exists (extend as needed).
    """
    primary_disease_id = get_primary_disease_id(db, disease_id)
    disease = db.get(Disease, primary_disease_id)
    if not disease:
        return False
    name = (disease.name or '').strip().lower()
    if kind == 'direct':
        return db.execute(
            select(1).select_from(DirectImageVerify)
            .where(and_(DirectImageVerify.image_upload_id == image_id,
                        DirectImageVerify.verified_status == 'verified'))
        ).first() is not None
    # encounter
    ef = db.get(EncounterFile, image_id)
    if not ef:
        return False
    enc = db.get(PatientEncounters, ef.patient_encounter_id)
    if not enc:
        return False
    if name in ('diabetic retinopathy', 'dr'):
        return (enc.dr_verified_status == 'verified') or (enc.encounter_verified_status == 'verified')
    if name == 'glaucoma':
        return (enc.glaucoma_verified_status == 'verified')
    # Future: 'amd' or others
    return False


def can_unverify_image(db, *, kind: str, image_id: int) -> bool:
    """
    Check if an image can be unverified (i.e., all its tasks are pending).
    Returns True if the image can be unverified, False otherwise.
    """
    if kind not in {'direct','encounter'}:
        raise ValueError('Invalid image kind')

    # Find all tasks for this image
    if kind == 'direct':
        tasks = db.execute(
            select(GradingTask).where(
                GradingTask.direct_image_upload_id == image_id
            )
        ).scalars().all()
    else:
        tasks = db.execute(
            select(GradingTask).where(
                GradingTask.encounter_file_id == image_id
            )
        ).scalars().all()

    # Check if all tasks are pending or if there are no tasks
    return all(task.state == 'pending' for task in tasks)


def create_or_get_task(
    db,
    *,
    kind: str,
    image_id: int,
    disease_id: int,
    lab_unit_id: int,
    create_linked: bool = True,
) -> GradingTask:
    """
    Idempotently create a grading task for (image_ref, disease_id, lab_unit_id).
    Guardrails:
      - Uniqueness is global per image×disease, independent of lab. If a task exists, reuse it and NEVER mutate its lab_unit_id.
      - If the existing task is final, treat it as gold standard; do not allow reassignment or duplication.
    Preconditions (caller must validate):
      - Image exists and is not locked (if app tracks locks)
      - Image is verified for the disease (_is_verified_for_disease)
    """
    if kind not in {'direct','encounter'}:
        raise ValueError('Invalid image kind')

    # Try to find an existing task first (global per image×disease)
    if kind == 'direct':
        existing = db.execute(
            select(GradingTask).where(
                GradingTask.direct_image_upload_id == image_id,
                GradingTask.disease_id == disease_id,
            )
        ).scalar_one_or_none()
    else:
        existing = db.execute(
            select(GradingTask).where(
                GradingTask.encounter_file_id == image_id,
                GradingTask.disease_id == disease_id,
            )
        ).scalar_one_or_none()

    if existing is not None:
        # Do not mutate lab_unit_id or reassign across labs
        task = existing
    else:
        # Create new task scoped to the provided lab unit
        if kind == 'direct':
            task = GradingTask(
                direct_image_upload_id=image_id,
                disease_id=disease_id,
                lab_unit_id=lab_unit_id,
                state='pending',
            )
        else:
            task = GradingTask(
                encounter_file_id=image_id,
                disease_id=disease_id,
                lab_unit_id=lab_unit_id,
                state='pending',
            )
        db.add(task)
        db.commit()
        db.refresh(task)

    if create_linked:
        linked_disease_ids = get_linked_disease_ids(db, disease_id)
        for linked_disease_id in linked_disease_ids:
            create_or_get_task(
                db,
                kind=kind,
                image_id=image_id,
                disease_id=linked_disease_id,
                lab_unit_id=lab_unit_id,
                create_linked=False,
            )
    return task


def remove_pending_tasks(db, *, kind: str, image_id: int) -> int:
    """
    Remove all pending grading tasks for an image.
    Returns the number of tasks removed.
    """
    if kind not in {'direct','encounter'}:
        raise ValueError('Invalid image kind')

    # Find all tasks for this image
    if kind == 'direct':
        tasks = db.execute(
            select(GradingTask).where(
                GradingTask.direct_image_upload_id == image_id
            )
        ).scalars().all()
    else:
        tasks = db.execute(
            select(GradingTask).where(
                GradingTask.encounter_file_id == image_id
            )
        ).scalars().all()

    # Remove only pending tasks
    removed_count = 0
    for task in tasks:
        if task.state == 'pending':
            db.delete(task)
            removed_count += 1
    
    if removed_count > 0:
        db.commit()
    
    return removed_count


def ensure_task(image_uuid: str, disease_id: int, db: Optional[OrmSession] = None) -> GradingTask:
    """
    Resolve image by UUID, verify gating, and create-or-return the task.
    Additional rules:
      - If a task already exists and is final, return it as-is; block any attempt to move/reassign labs.
      - Never change lab_unit_id on an existing task.
    """
    if db is None:
        with transaction_scope() as scoped_db:
            return _ensure_task_with_db(scoped_db, image_uuid, disease_id)
    return _ensure_task_with_db(db, image_uuid, disease_id)


def _ensure_task_with_db(db: OrmSession, image_uuid: str, disease_id: int) -> GradingTask:
    kind, image_id, lab_unit_id = _resolve_image_by_uuid(db, image_uuid)
    # Optional: check lock flags
    if kind == 'direct':
        diu = db.get(DirectImageUpload, image_id)
        if getattr(diu, 'is_locked', False):
            raise PermissionError('Image is locked')
    else:
        ef = db.get(EncounterFile, image_id)
        if getattr(ef, 'is_locked', False):
            raise PermissionError('Image is locked')
    if not _is_verified_for_disease(db, kind, image_id, disease_id):
        raise PermissionError('Image not verified for this disease')
    task = create_or_get_task(db, kind=kind, image_id=image_id, disease_id=disease_id, lab_unit_id=lab_unit_id)
    # Gold standard guard: do not permit cross-lab reassignment after final
    if task.state == 'final' and task.lab_unit_id != lab_unit_id:
        # Visible to callers for UX feedback; also log via app success/error loggers in real implementation
        raise PermissionError('Gold standard already set - cross-lab reassignment is disabled for finalized tasks')
    return task
