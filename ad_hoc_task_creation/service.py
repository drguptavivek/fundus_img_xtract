from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from auth.utils import utcnow
from authz.context import access_context
from authz.scopes import RecordScope, admin_scope, assigned_lab_scope
from grading.workbench.linked_tasks import get_primary_disease_id
from models import (
    AdHocTaskCreation,
    DirectImageUpload,
    Disease,
    EncounterFile,
    GradingTask,
    LabUnit,
    PatientEncounters,
    User,
)

from .dtos import (
    AuthorizedSource,
    CreateAdHocTasksCommand,
    CreateResult,
    SourceReference,
)
from .errors import conflict, denied, invalid


def require_creator(*, db, actor: User) -> None:
    context = access_context(db, actor)
    if admin_scope(context).allowed:
        return
    if not context.has_any_global_role(frozenset({"data_manager"})):
        raise denied()


def allowed_classical_lab_unit_ids(*, db, actor: User) -> frozenset[int]:
    require_creator(db=db, actor=actor)
    context = access_context(db, actor)
    if admin_scope(context).allowed:
        return frozenset(db.execute(select(LabUnit.id)).scalars())
    return context.assigned_lab_unit_ids


def validate_filter_scope(
    *, db, actor: User, hospital_id: int | None, lab_unit_id: int | None
) -> frozenset[int]:
    allowed = allowed_classical_lab_unit_ids(db=db, actor=actor)
    if not allowed:
        raise denied("No classical Lab Units are authorized for ad-hoc task creation.")
    allowed_rows = db.execute(
        select(LabUnit.id, LabUnit.hospital_id).where(LabUnit.id.in_(allowed))
    ).all()
    allowed_hospitals = {row.hospital_id for row in allowed_rows}
    if lab_unit_id is not None and lab_unit_id not in allowed:
        raise denied("The supplied Lab Unit is outside the authorized classical scope.")
    if hospital_id is not None and hospital_id not in allowed_hospitals:
        raise denied("The supplied Hospital is outside the authorized classical scope.")
    if lab_unit_id is not None and hospital_id is not None:
        lab = db.get(LabUnit, lab_unit_id)
        if lab is None or lab.hospital_id != hospital_id:
            raise invalid("The supplied Lab Unit does not belong to the supplied Hospital.")
    return allowed


def authorize_source(
    *, db, actor: User, reference: SourceReference, lock: bool = False
) -> AuthorizedSource:
    require_creator(db=db, actor=actor)
    if reference.source == "direct":
        query = select(DirectImageUpload).where(
            DirectImageUpload.id == reference.source_id
        )
        if lock:
            query = query.with_for_update()
        source = db.execute(query).scalar_one_or_none()
        if source is None:
            raise invalid("A selected direct image does not exist.")
        project_id = source.project_id
        lab_unit_id = source.lab_unit_id
        hospital_id = source.hospital_id
    else:
        query = (
            select(EncounterFile)
            .where(EncounterFile.id == reference.source_id)
        )
        if lock:
            query = query.with_for_update()
        source = db.execute(query).scalar_one_or_none()
        if source is None:
            raise invalid("A selected ZIP image does not exist.")
        encounter = db.get(PatientEncounters, source.patient_encounter_id)
        if encounter is None:
            raise invalid("A selected ZIP image has no encounter lineage.")
        if encounter.lab_unit_id is None or source.lab_unit_id is None:
            raise invalid("A selected ZIP image has incomplete encounter lineage.")
        if encounter.lab_unit_id != source.lab_unit_id:
            raise invalid(
                "A selected ZIP image does not belong to its encounter Lab Unit."
            )
        project_id = source.project_id if source.project_id is not None else encounter.project_id
        lab_unit_id = source.lab_unit_id
        hospital_id = source.hospital_id
        if hospital_id is None and lab_unit_id is not None:
            lab = db.get(LabUnit, lab_unit_id)
            hospital_id = lab.hospital_id if lab else None
    if project_id is not None:
        raise denied("Project records cannot be used for ad-hoc task creation.")
    if lab_unit_id is None or hospital_id is None:
        raise invalid("A selected source has incomplete classical lineage.")
    lab = db.get(LabUnit, lab_unit_id)
    if lab is None or lab.hospital_id != hospital_id:
        raise invalid("A selected source has inconsistent Lab Unit lineage.")
    context = access_context(db, actor)
    if not admin_scope(context).allowed and not assigned_lab_scope(
        context,
        {"data_manager"},
        RecordScope.classical(lab_unit_id=lab_unit_id, hospital_id=hospital_id),
    ).allowed:
        raise denied("A selected source is outside the authorized classical scope.")
    return AuthorizedSource(
        source=reference.source,
        source_id=reference.source_id,
        lab_unit_id=lab_unit_id,
        hospital_id=hospital_id,
    )


def authorize_sources(*, db, actor: User, references, lock: bool = False):
    return tuple(
        authorize_source(db=db, actor=actor, reference=reference, lock=lock)
        for reference in references
    )


def validate_root_diseases(db, disease_ids: tuple[int, ...]) -> None:
    existing = set(
        db.execute(select(Disease.id).where(Disease.id.in_(disease_ids))).scalars()
    )
    if existing != set(disease_ids):
        raise invalid("A selected disease does not exist.")
    for disease_id in disease_ids:
        if get_primary_disease_id(db, disease_id) != disease_id:
            raise invalid(
                "Linked diseases cannot be selected directly; create the parent disease task."
            )


def create_tasks(*, db, actor: User, command: CreateAdHocTasksCommand) -> CreateResult:
    validate_root_diseases(db, command.disease_ids)
    sources = authorize_sources(
        db=db, actor=actor, references=command.references, lock=True
    )
    conflicts: list[str] = []
    for source in sources:
        source_column = (
            GradingTask.direct_image_upload_id
            if source.source == "direct"
            else GradingTask.encounter_file_id
        )
        existing = db.execute(
            select(GradingTask.id).where(
                source_column == source.source_id,
                GradingTask.disease_id.in_(command.disease_ids),
            )
        ).scalars().all()
        if existing:
            conflicts.append(f"{source.source}:{source.source_id}")
    if conflicts:
        raise conflict("One or more selected sources already has a requested task.")

    canonical_refs = [
        {"source": item.source, "id": item.source_id} for item in sources
    ]
    try:
        with db.begin_nested():
            batch = AdHocTaskCreation(
                created_by_id=actor.id,
                created_at=utcnow(),
                diseases_json=json.dumps(list(command.disease_ids)),
                max_images=command.max_images,
                filters_json=json.dumps(command.filters),
                selected_image_refs_json=json.dumps(canonical_refs),
                randomized=command.randomize or None,
                remarks=command.remarks,
            )
            db.add(batch)
            db.flush()
            created = 0
            for source in sources:
                for disease_id in command.disease_ids:
                    task = GradingTask(
                        uuid=str(uuid4()),
                        disease_id=disease_id,
                        lab_unit_id=source.lab_unit_id,
                        state="pending",
                        ad_hoc_id=batch.id,
                        task_source="ad_hoc",
                        grading_target_level="image",
                    )
                    if source.source == "direct":
                        task.direct_image_upload_id = source.source_id
                    else:
                        task.encounter_file_id = source.source_id
                    db.add(task)
                    created += 1
            batch.summary_json = json.dumps(
                {"created": created, "duplicates": 0, "unsuitable": 0, "errors": 0}
            )
            db.flush()
    except IntegrityError as exc:
        raise conflict(
            "A selected source acquired the requested task concurrently."
        ) from exc
    return CreateResult(batch_id=batch.id, created=created)
