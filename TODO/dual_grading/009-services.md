# Services — Task Creation and Verification Gating (Draft)

Purpose
- Provide reusable, testable functions for creating grading tasks, enforcing verification gating, and idempotent ensure‑task behavior. Keep all DB sessions explicit and closed. No PHI touched.

Conventions
- Use `with Session() as db:` where the caller does not pass a session.
- When the caller passes `db`, never close it in the service.
- Raise typed errors (ValueError/PermissionError/RuntimeError) with safe messages; callers map to HTTP 4xx/5xx and flash toasts.

Imports
```python
from sqlalchemy import select, exists, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from typing import Optional, Tuple

from models import (
    Session, GradingTask, Grade, Consensus, DirectImageUpload, DirectImageVerify,
    EncounterFile, PatientEncounters, Disease, DiseaseGrading, LabUnit
)
```

Helpers
```python
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
    disease = db.get(Disease, disease_id)
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
        return (enc.dr_verified_status == 'verified')
    if name == 'glaucoma':
        return (enc.glaucoma_verified_status == 'verified')
    # Future: 'amd' or others
    return False
```

Service: create_or_get_task
```python
def create_or_get_task(db, *, kind: str, image_id: int, disease_id: int, lab_unit_id: int) -> GradingTask:
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
        return existing

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
    return task
```

Service: ensure_task (by UUID)
```python
def ensure_task(image_uuid: str, disease_id: int) -> GradingTask:
    """
    Resolve image by UUID, verify gating, and create-or-return the task.
    Additional rules:
      - If a task already exists and is final, return it as-is; block any attempt to move/reassign labs.
      - Never change lab_unit_id on an existing task.
    """
    with Session() as db:
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
            raise PermissionError('This image already has a final consensus for the disease; cross-lab reassignment is disabled')
        return task
```

Notes
- Callers performing UI actions should combine eligibility checks (user has proper slot per `UserDiseaseUnitRole`) before invoking `ensure_task`.
- For bulk/admin backfills, iterate known verified images and call `create_or_get_task` directly within a single session/transaction window when feasible.
- Never update `lab_unit_id` of an existing task; if queues need to hide/show across labs, handle it at query time using the task’s lab_unit_id and the user’s eligibility. A final task is the gold standard and should not be recreated or reassigned in another lab unit.

