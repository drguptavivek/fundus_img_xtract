from __future__ import annotations

from datetime import date
from hashlib import sha256

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth.utils import utcnow
from encounter_sets.models import EncounterSetAttachment
from grading.workbench.models import (
    GradingSubmissionEventItem,
    GradingWorkbenchSession,
    GradingWorkbenchSessionTarget,
)
from models import (
    Consensus,
    EncounterSetGradingPackage,
    EncounterSetGradingSubmission,
    EncounterSetImage,
    Grade,
    GradingTask,
    IntraRaterTask,
    PatientEncounters,
    Project,
    RemidioExam,
    SensitiveOperationAudit,
)
from remidio_api_integration.models import (
    ProjectUploadProfileRemidioApiBinding,
    RemidioApiExamEncounter,
)
from upload_profiles.models import ProjectUploadProfile, UploadProfile

from .dtos import (
    CaptureDateDTO,
    EncounterDTO,
    MigrationPreviewDTO,
    MigrationResultDTO,
    ProjectDTO,
)
from .exceptions import RemidioEncounterMigrationError


def list_projects(db: Session) -> tuple[ProjectDTO, ...]:
    rows = db.query(Project).filter(Project.active.is_(True)).order_by(Project.title).all()
    return tuple(ProjectDTO(id=row.id, title=row.title, code=row.code) for row in rows)


def list_capture_dates(db: Session, *, source_project_id: int) -> tuple[CaptureDateDTO, ...]:
    _project(db, source_project_id)
    rows = (
        db.query(PatientEncounters.capture_date_dt, func.count(PatientEncounters.id))
        .join(RemidioApiExamEncounter, RemidioApiExamEncounter.patient_encounter_id == PatientEncounters.id)
        .filter(
            PatientEncounters.project_id == source_project_id,
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.capture_date_dt.isnot(None),
        )
        .group_by(PatientEncounters.capture_date_dt)
        .order_by(PatientEncounters.capture_date_dt.desc())
        .all()
    )
    return tuple(CaptureDateDTO(date=row_date, encounter_count=count) for row_date, count in rows)


def list_encounters(
    db: Session,
    *,
    source_project_id: int,
    capture_date: date,
) -> tuple[EncounterDTO, ...]:
    _project(db, source_project_id)
    encounters = _source_encounters(db, source_project_id, capture_date)
    return _encounter_dtos(db, encounters)


def preview_migration(
    db: Session,
    *,
    source_project_id: int,
    target_project_id: int,
    capture_date: date,
    encounter_ids: tuple[int, ...],
) -> MigrationPreviewDTO:
    if source_project_id == target_project_id:
        raise RemidioEncounterMigrationError("Source and target projects must be different.")
    source_project = _project(db, source_project_id)
    target_project = _project(db, target_project_id)
    normalized_ids = _normalize_ids(encounter_ids)
    encounters = _selected_encounters(db, source_project_id, capture_date, normalized_ids)
    encounter_rows = _encounter_dtos(db, encounters)
    blocked = [row for row in encounter_rows if not row.movable]
    if blocked:
        raise RemidioEncounterMigrationError(
            "One or more EncounterSets have immutable grading history and cannot be moved.",
            status_code=409,
            details={"encounters": [row.to_dict() for row in blocked]},
        )

    mapping, binding_by_encounter, warnings = _resolve_target_lineage(
        db,
        target_project_id=target_project_id,
        encounters=encounters,
    )
    task_count = sum(row.task_count for row in encounter_rows)
    grade_count = sum(row.grade_count for row in encounter_rows)
    package_count = sum(row.package_count for row in encounter_rows)
    token = _confirmation_token(
        source_project_id,
        target_project_id,
        capture_date,
        normalized_ids,
        task_count,
        grade_count,
        package_count,
        mapping.id,
        tuple(sorted(row.id for row in binding_by_encounter.values())),
    )
    return MigrationPreviewDTO(
        source_project=ProjectDTO(source_project.id, source_project.title, source_project.code),
        target_project=ProjectDTO(target_project.id, target_project.title, target_project.code),
        capture_date=capture_date,
        encounters=encounter_rows,
        target_project_upload_profile_id=mapping.id,
        target_upload_profile_id=mapping.upload_profile_id,
        target_upload_profile_name=mapping.profile.name,
        target_binding_ids=tuple(sorted({row.id for row in binding_by_encounter.values()})),
        warnings=tuple(warnings),
        confirmation_token=token,
        task_count=task_count,
        grade_count=grade_count,
        package_count=package_count,
    )


def apply_migration(
    db: Session,
    *,
    actor_user_id: int,
    source_project_id: int,
    target_project_id: int,
    capture_date: date,
    encounter_ids: tuple[int, ...],
    confirmation_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MigrationResultDTO:
    normalized_ids = _normalize_ids(encounter_ids)
    locked = (
        db.query(PatientEncounters)
        .filter(PatientEncounters.id.in_(normalized_ids))
        .with_for_update()
        .all()
    )
    if len(locked) != len(normalized_ids):
        raise RemidioEncounterMigrationError("One or more selected EncounterSets no longer exist.", status_code=409)

    preview = preview_migration(
        db,
        source_project_id=source_project_id,
        target_project_id=target_project_id,
        capture_date=capture_date,
        encounter_ids=normalized_ids,
    )
    if confirmation_token != preview.confirmation_token:
        raise RemidioEncounterMigrationError(
            "The migration preview is stale. Preview the selection again before moving it.",
            status_code=409,
        )

    encounters = sorted(locked, key=lambda row: row.id)
    mapping, binding_by_encounter, _warnings = _resolve_target_lineage(
        db,
        target_project_id=target_project_id,
        encounters=encounters,
    )
    task_ids, package_ids = _work_ids(db, normalized_ids)
    grade_count = db.query(Grade).filter(Grade.task_id.in_(task_ids)).count() if task_ids else 0

    sessions_invalidated = _invalidate_sessions(db, task_ids, package_ids)
    if package_ids:
        packages = db.query(EncounterSetGradingPackage).filter(EncounterSetGradingPackage.id.in_(package_ids)).all()
        for package in packages:
            db.delete(package)
        db.flush()
    remaining_tasks = db.query(GradingTask).filter(GradingTask.id.in_(task_ids)).all() if task_ids else []
    for task in remaining_tasks:
        db.delete(task)
    db.flush()

    moved_at = utcnow()
    associations = {
        row.patient_encounter_id: row
        for row in db.query(RemidioApiExamEncounter)
        .filter(RemidioApiExamEncounter.patient_encounter_id.in_(normalized_ids))
        .all()
    }
    for encounter in encounters:
        association = associations[encounter.id]
        target_binding = binding_by_encounter[encounter.id]
        old_verification = dict((encounter.metadata_json or {}).get("verification") or {})
        metadata = dict(encounter.metadata_json or {})
        history = list(metadata.get("project_migration_history") or [])
        history.append({
            "moved_at": moved_at.isoformat(),
            "moved_by_user_id": actor_user_id,
            "source_project_id": source_project_id,
            "target_project_id": target_project_id,
            "source_upload_profile_id": encounter.upload_profile_id,
            "target_upload_profile_id": mapping.upload_profile_id,
            "source_project_upload_profile_id": association.project_upload_profile_id,
            "target_project_upload_profile_id": mapping.id,
            "source_remidio_api_binding_id": association.remidio_api_binding_id,
            "target_remidio_api_binding_id": target_binding.id,
            "previous_verification": old_verification,
        })
        metadata["project_migration_history"] = history
        metadata["project_upload_profile_id"] = mapping.id
        metadata["remidio_api_binding_id"] = target_binding.id
        metadata["verification"] = {
            "status": "pending",
            "reset_reason": "remidio_api_project_migration",
            "reset_at": moved_at.isoformat(),
            "reset_by_user_id": actor_user_id,
        }
        encounter.metadata_json = metadata
        encounter.project_id = target_project_id
        encounter.upload_profile_id = mapping.upload_profile_id
        encounter.encounter_verified_status = None
        encounter.encounter_verified_by = None
        encounter.encounter_verified_at = None
        association.project_upload_profile_id = mapping.id
        association.remidio_api_binding_id = target_binding.id

    db.query(EncounterSetImage).filter(EncounterSetImage.patient_encounter_id.in_(normalized_ids)).update(
        {EncounterSetImage.project_id: target_project_id},
        synchronize_session=False,
    )
    db.query(EncounterSetAttachment).filter(EncounterSetAttachment.patient_encounter_id.in_(normalized_ids)).update(
        {EncounterSetAttachment.project_id: target_project_id, EncounterSetAttachment.upload_profile_id: mapping.upload_profile_id},
        synchronize_session=False,
    )

    audit = SensitiveOperationAudit(
        user_id=actor_user_id,
        operation_type="remidio_api_encounter_project_migration",
        status="completed",
        ip_address=(ip_address or "")[:45] or None,
        user_agent=(user_agent or "")[:500] or None,
    )
    audit.set_request_details({
        "source_project_id": source_project_id,
        "target_project_id": target_project_id,
        "capture_date": capture_date.isoformat(),
        "encounter_ids": list(normalized_ids),
        "confirmation_token": confirmation_token,
    })
    audit.set_result_details({
        "moved_count": len(normalized_ids),
        "tasks_reset": len(task_ids),
        "grades_reset": grade_count,
        "packages_reset": len(package_ids),
        "sessions_invalidated": sessions_invalidated,
        "target_project_upload_profile_id": mapping.id,
        "target_binding_ids": sorted({row.id for row in binding_by_encounter.values()}),
    })
    db.add(audit)
    db.flush()
    return MigrationResultDTO(
        moved_encounter_ids=normalized_ids,
        source_project_id=source_project_id,
        target_project_id=target_project_id,
        tasks_reset=len(task_ids),
        grades_reset=grade_count,
        packages_reset=len(package_ids),
        sessions_invalidated=sessions_invalidated,
        audit_id=audit.id,
    )


def _source_encounters(db: Session, source_project_id: int, capture_date: date):
    return (
        db.query(PatientEncounters)
        .join(RemidioApiExamEncounter, RemidioApiExamEncounter.patient_encounter_id == PatientEncounters.id)
        .filter(
            PatientEncounters.project_id == source_project_id,
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.capture_date_dt == capture_date,
        )
        .order_by(PatientEncounters.id)
        .all()
    )


def _selected_encounters(db, source_project_id, capture_date, encounter_ids):
    rows = (
        db.query(PatientEncounters)
        .join(RemidioApiExamEncounter, RemidioApiExamEncounter.patient_encounter_id == PatientEncounters.id)
        .filter(
            PatientEncounters.id.in_(encounter_ids),
            PatientEncounters.project_id == source_project_id,
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.capture_date_dt == capture_date,
        )
        .order_by(PatientEncounters.id)
        .all()
    )
    by_id = {row.id: row for row in rows}
    if any(encounter_id not in by_id for encounter_id in encounter_ids):
        raise RemidioEncounterMigrationError(
            "The selection contains an EncounterSet outside the chosen source project or capture date.",
            status_code=409,
        )
    return [by_id[encounter_id] for encounter_id in encounter_ids]


def _encounter_dtos(db: Session, encounters) -> tuple[EncounterDTO, ...]:
    if not encounters:
        return ()
    encounter_ids = [row.id for row in encounters]
    image_rows = db.query(EncounterSetImage.id, EncounterSetImage.patient_encounter_id).filter(
        EncounterSetImage.patient_encounter_id.in_(encounter_ids)
    ).all()
    image_to_encounter = {image_id: encounter_id for image_id, encounter_id in image_rows}
    image_counts = _counts(encounter_id for _image_id, encounter_id in image_rows)
    image_ids = list(image_to_encounter)

    tasks = db.query(GradingTask).filter(or_(
        GradingTask.patient_encounter_id.in_(encounter_ids),
        GradingTask.encounter_set_image_id.in_(image_ids) if image_ids else False,
    )).all()
    task_to_encounter = {
        task.id: task.patient_encounter_id or image_to_encounter.get(task.encounter_set_image_id)
        for task in tasks
    }
    task_counts = _counts(value for value in task_to_encounter.values() if value is not None)
    task_ids = list(task_to_encounter)
    grade_counts: dict[int, int] = {}
    if task_ids:
        grade_rows = (
            db.query(Grade.task_id, func.count(Grade.id))
            .filter(Grade.task_id.in_(task_ids))
            .group_by(Grade.task_id)
            .all()
        )
        for task_id, count in grade_rows:
            encounter_id = task_to_encounter[task_id]
            grade_counts[encounter_id] = grade_counts.get(encounter_id, 0) + int(count)

    package_rows = db.query(
        EncounterSetGradingPackage.id,
        EncounterSetGradingPackage.patient_encounter_id,
    ).filter(EncounterSetGradingPackage.patient_encounter_id.in_(encounter_ids)).all()
    package_to_encounter = {package_id: encounter_id for package_id, encounter_id in package_rows}
    package_counts = _counts(package_to_encounter.values())
    package_ids = list(package_to_encounter)

    attachment_counts = dict(
        db.query(EncounterSetAttachment.patient_encounter_id, func.count(EncounterSetAttachment.id))
        .filter(EncounterSetAttachment.patient_encounter_id.in_(encounter_ids))
        .group_by(EncounterSetAttachment.patient_encounter_id)
        .all()
    )
    exam_ids = dict(
        db.query(RemidioApiExamEncounter.patient_encounter_id, RemidioExam.remidio_exam_id)
        .join(RemidioExam, RemidioExam.id == RemidioApiExamEncounter.remidio_exam_id)
        .filter(RemidioApiExamEncounter.patient_encounter_id.in_(encounter_ids))
        .all()
    )

    blockers: dict[int, list[str]] = {encounter_id: [] for encounter_id in encounter_ids}
    if package_ids:
        submitted_package_ids = {
            row[0] for row in db.query(EncounterSetGradingSubmission.encounter_set_package_id)
            .filter(EncounterSetGradingSubmission.encounter_set_package_id.in_(package_ids))
            .distinct().all()
        }
        for package_id in submitted_package_ids:
            blockers[package_to_encounter[package_id]].append("Completed package submission exists.")
    if task_ids:
        blocker_queries = (
            (
                "Immutable workbench submission history exists.",
                db.query(GradingSubmissionEventItem.task_id).filter(GradingSubmissionEventItem.task_id.in_(task_ids)).distinct().all(),
            ),
            (
                "Consensus result exists.",
                db.query(Consensus.task_id).filter(Consensus.task_id.in_(task_ids)).distinct().all(),
            ),
            (
                "Intra-rater work references a source task.",
                db.query(IntraRaterTask.source_task_id).filter(IntraRaterTask.source_task_id.in_(task_ids)).distinct().all(),
            ),
        )
        for message, rows in blocker_queries:
            for encounter_id in {task_to_encounter[row[0]] for row in rows}:
                blockers[encounter_id].append(message)

    return tuple(
        EncounterDTO(
            id=encounter.id,
            uuid=encounter.uuid,
            remidio_exam_id=str(exam_ids.get(encounter.id) or ""),
            capture_date=encounter.capture_date_dt,
            verification_status=encounter.encounter_verified_status or "pending",
            image_count=image_counts.get(encounter.id, 0),
            attachment_count=attachment_counts.get(encounter.id, 0),
            task_count=task_counts.get(encounter.id, 0),
            grade_count=grade_counts.get(encounter.id, 0),
            package_count=package_counts.get(encounter.id, 0),
            movable=not blockers[encounter.id],
            blockers=tuple(blockers[encounter.id]),
        )
        for encounter in encounters
    )


def _counts(values) -> dict[int, int]:
    result: dict[int, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _resolve_target_lineage(db: Session, *, target_project_id: int, encounters):
    binding_by_encounter = {}
    mapping_ids = set()
    warnings = []
    encounter_ids = [encounter.id for encounter in encounters]
    association_rows = (
        db.query(RemidioApiExamEncounter, ProjectUploadProfileRemidioApiBinding.remidio_api_source_rule_id)
        .join(
            ProjectUploadProfileRemidioApiBinding,
            ProjectUploadProfileRemidioApiBinding.id == RemidioApiExamEncounter.remidio_api_binding_id,
        )
        .filter(RemidioApiExamEncounter.patient_encounter_id.in_(encounter_ids))
        .all()
    )
    association_by_encounter = {association.patient_encounter_id: association for association, _rule_id in association_rows}
    rule_by_encounter = {association.patient_encounter_id: rule_id for association, rule_id in association_rows}
    if len(association_by_encounter) != len(encounter_ids):
        raise RemidioEncounterMigrationError(
            "One or more selected EncounterSets no longer have complete Remidio routing lineage.",
            status_code=409,
        )
    target_candidates = (
        db.query(ProjectUploadProfileRemidioApiBinding)
        .join(ProjectUploadProfile)
        .join(UploadProfile)
        .filter(
            ProjectUploadProfile.project_id == target_project_id,
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.remidio_api_source_rule_id.in_(set(rule_by_encounter.values())),
        )
        .order_by(ProjectUploadProfileRemidioApiBinding.active.desc(), ProjectUploadProfileRemidioApiBinding.id.desc())
        .all()
    )
    candidates_by_rule: dict[int, list[ProjectUploadProfileRemidioApiBinding]] = {}
    for candidate in target_candidates:
        candidates_by_rule.setdefault(candidate.remidio_api_source_rule_id, []).append(candidate)
    for encounter in encounters:
        candidates = candidates_by_rule.get(rule_by_encounter[encounter.id], [])
        covering = [row for row in candidates if row.active_from_date <= encounter.capture_date_dt and (row.active_to_date is None or row.active_to_date >= encounter.capture_date_dt)]
        chosen_pool = covering or candidates
        mapping_pool = {row.project_upload_profile_id for row in chosen_pool}
        if not chosen_pool:
            raise RemidioEncounterMigrationError(
                f"Target project has no Remidio API binding for EncounterSet {encounter.id}'s source route.",
                status_code=409,
            )
        if len(mapping_pool) != 1:
            raise RemidioEncounterMigrationError(
                f"Target project has ambiguous Remidio API profile mappings for EncounterSet {encounter.id}.",
                status_code=409,
            )
        chosen = chosen_pool[0]
        if not covering:
            warnings.append(
                f"Historical target binding {chosen.id} did not cover {encounter.capture_date_dt.isoformat()}."
            )
        elif not chosen.active:
            warnings.append(
                f"Inactive historical target binding {chosen.id} will be used for this correction."
            )
        binding_by_encounter[encounter.id] = chosen
        mapping_ids.add(chosen.project_upload_profile_id)
    if len(mapping_ids) != 1:
        raise RemidioEncounterMigrationError(
            "Selected EncounterSets resolve to different target upload profiles. Move them in separate batches.",
            status_code=409,
        )
    mapping = (
        db.query(ProjectUploadProfile)
        .join(UploadProfile)
        .filter(ProjectUploadProfile.id == next(iter(mapping_ids)))
        .one()
    )
    return mapping, binding_by_encounter, list(dict.fromkeys(warnings))


def _work_ids(db: Session, encounter_ids: tuple[int, ...]):
    image_ids = [row[0] for row in db.query(EncounterSetImage.id).filter(EncounterSetImage.patient_encounter_id.in_(encounter_ids)).all()]
    task_ids = [row[0] for row in db.query(GradingTask.id).filter(or_(
        GradingTask.patient_encounter_id.in_(encounter_ids),
        GradingTask.encounter_set_image_id.in_(image_ids) if image_ids else False,
    )).all()]
    package_ids = [row[0] for row in db.query(EncounterSetGradingPackage.id).filter(EncounterSetGradingPackage.patient_encounter_id.in_(encounter_ids)).all()]
    return task_ids, package_ids


def _invalidate_sessions(db: Session, task_ids: list[int], package_ids: list[int]) -> int:
    session_ids = set()
    if task_ids:
        session_ids.update(row[0] for row in db.query(GradingWorkbenchSessionTarget.session_id).filter(GradingWorkbenchSessionTarget.task_id.in_(task_ids)).all())
        session_ids.update(row[0] for row in db.query(GradingWorkbenchSession.id).filter(GradingWorkbenchSession.root_task_id.in_(task_ids)).all())
    if package_ids:
        session_ids.update(row[0] for row in db.query(GradingWorkbenchSession.id).filter(GradingWorkbenchSession.encounter_set_package_id.in_(package_ids)).all())
    if not session_ids:
        return 0
    now = utcnow()
    db.query(GradingWorkbenchSessionTarget).filter(
        GradingWorkbenchSessionTarget.session_id.in_(session_ids),
        GradingWorkbenchSessionTarget.released_at.is_(None),
    ).update({
        GradingWorkbenchSessionTarget.released_at: now,
        GradingWorkbenchSessionTarget.release_reason: "project_move",
    }, synchronize_session=False)
    return db.query(GradingWorkbenchSession).filter(
        GradingWorkbenchSession.id.in_(session_ids),
        GradingWorkbenchSession.status == "active",
    ).update({
        GradingWorkbenchSession.status: "invalidated",
        GradingWorkbenchSession.invalidated_at: now,
        GradingWorkbenchSession.close_reason: "project_move",
    }, synchronize_session=False)


def _project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or not project.active:
        raise RemidioEncounterMigrationError("Project not found.", status_code=404)
    return project


def _normalize_ids(encounter_ids: tuple[int, ...]) -> tuple[int, ...]:
    values = tuple(sorted(set(int(value) for value in encounter_ids)))
    if not values:
        raise RemidioEncounterMigrationError("Select at least one EncounterSet.")
    if len(values) > 300:
        raise RemidioEncounterMigrationError("A migration may contain at most 300 EncounterSets.")
    return values


def _confirmation_token(
    source_project_id,
    target_project_id,
    capture_date,
    encounter_ids,
    task_count,
    grade_count,
    package_count,
    target_mapping_id,
    target_binding_ids,
):
    material = ":".join([
        str(source_project_id),
        str(target_project_id),
        capture_date.isoformat(),
        ",".join(str(value) for value in encounter_ids),
        str(task_count),
        str(grade_count),
        str(package_count),
        str(target_mapping_id),
        ",".join(str(value) for value in target_binding_ids),
    ])
    digest = sha256(material.encode("utf-8")).hexdigest()[:10].upper()
    return f"MOVE-{len(encounter_ids)}-{digest}"
