"""Frozen EncounterSet package runtime owned by the grading workbench."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from auth.utils import utcnow
from models import (
    Consensus,
    DiseaseGrading,
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    EncounterSetGradingSubmission,
    EncounterSetGradingSubmissionItem,
    Grade,
    GradingTask,
)
from .revision_policy import REVISION_WINDOW
from .roles import HUMAN_ROLE_SLOTS


class EncounterSetGradingError(ValueError):
    pass


class StaleEncounterSetPackageError(EncounterSetGradingError):
    pass


def can_view_package_record(db, package: EncounterSetGradingPackage, *, user_id: int) -> bool:
    """Require a current grading allocation for at least one frozen target."""
    from grading_allocation.eligibility import is_user_eligible_for_task

    return any(
        is_user_eligible_for_task(
            db,
            user_id=user_id,
            task=task,
            role_slot=role_slot,
        )
        for task in package.tasks
        for role_slot in HUMAN_ROLE_SLOTS
    )


def ordered_package_tasks(tasks: list[GradingTask]) -> list[GradingTask]:
    """Stable package pager order: scope, images by eye/position, encounter."""
    return sorted(
        tasks,
        key=lambda task: (
            task.encounter_set_scope.display_order if task.encounter_set_scope else 0,
            1 if task.grading_target_level == "encounter" else 0,
            _laterality_order(task),
            task.encounter_set_image.spatial_position if task.encounter_set_image else 0,
            task.disease.name if task.disease else "",
            task.id,
        ),
    )


def _laterality_order(task: GradingTask) -> int:
    image = task.encounter_set_image
    metadata = image.metadata_json if image and image.metadata_json else {}
    value = str(metadata.get("laterality") or metadata.get("eye") or "").strip().lower()
    if value in {"od", "right", "right eye", "r"}:
        return 0
    if value in {"os", "left", "left eye", "l"}:
        return 1
    return 2


@dataclass(frozen=True)
class TargetGradeInputDTO:
    task_uuid: str
    disease_grading_id: int
    comment: str
    selected_features_json: str | None
    feature_geometry_json: dict | None


@dataclass(frozen=True)
class EncounterSetSubmissionInputDTO:
    package_uuid: str
    role_slot: str
    grader_user_id: int
    expected_package_revision: int
    targets: tuple[TargetGradeInputDTO, ...]


def editable_tasks(
    package: EncounterSetGradingPackage,
    role_slot: str,
    grader_user_id: int,
    *,
    now=None,
) -> list[GradingTask]:
    if role_slot not in HUMAN_ROLE_SLOTS:
        return []
    now = now or utcnow()
    first_submission = _first_submission(package, role_slot, grader_user_id)
    within_revision = bool(
        first_submission and now < first_submission.created_at + REVISION_WINDOW
    )
    partial_graders = {
        grade.grader_user_id
        for task in package.tasks
        for grade in task.grades
        if grade.role_slot == role_slot
    }
    if first_submission is None and partial_graders and partial_graders != {grader_user_id}:
        return []
    if role_slot == "resident2" and complete_package_submission(package, "resident") is None:
        return []
    if role_slot == "arbitrator" and complete_package_submission(package, "resident2") is None:
        return []
    result = []
    for scope in package.scopes:
        if role_slot == "arbitrator":
            can_revise_adjudication = (
                scope.state == "final"
                and _scope_has_adjudication(scope)
                and first_submission is not None
                and within_revision
            )
            if scope.state != "arbitration" and not can_revise_adjudication:
                continue
        else:
            if _scope_has_adjudication(scope):
                continue
            if first_submission and not within_revision:
                continue
        result.extend(scope.tasks)
    return result


def complete_package_submission(
    package: EncounterSetGradingPackage,
    role_slot: str,
) -> EncounterSetGradingSubmission | None:
    """Return a complete stage submission that covers its required package targets."""
    required_task_ids = {task.id for task in package.tasks}
    candidates = sorted(
        (
            event
            for event in package.submissions
            if event.role_slot == role_slot and event.is_complete
        ),
        key=lambda event: event.created_at,
    )
    for event in candidates:
        submitted_task_ids = {item.task_id for item in event.items}
        if (role_slot == "arbitrator" and submitted_task_ids) or submitted_task_ids == required_task_ids:
            return event
    return None


def submit_package(
    db, package: EncounterSetGradingPackage, submission: EncounterSetSubmissionInputDTO
) -> EncounterSetGradingSubmission:
    if submission.role_slot not in HUMAN_ROLE_SLOTS:
        raise EncounterSetGradingError("Invalid package role slot.")
    reconcile_package_state(db, package)
    if package.revision_number != submission.expected_package_revision:
        raise StaleEncounterSetPackageError(
            "This package changed after it was opened. Reload before submitting."
        )
    _validate_role_owner(package, submission.role_slot, submission.grader_user_id)
    editable = editable_tasks(package, submission.role_slot, submission.grader_user_id)
    editable_by_uuid = {task.uuid: task for task in editable}
    supplied = {target.task_uuid: target for target in submission.targets}
    if not editable_by_uuid:
        raise EncounterSetGradingError("No package targets are currently editable.")
    if set(supplied) != set(editable_by_uuid):
        raise EncounterSetGradingError(
            "Submit one grade for every editable target in this package."
        )

    for scope in package.scopes:
        if len([
            task for task in scope.tasks if task.grading_target_level == "encounter"
        ]) != 1:
            raise EncounterSetGradingError(
                "Every runtime scope must contain exactly one set-level target."
            )
    labels_by_task_uuid = {}
    for task_uuid, task in editable_by_uuid.items():
        target = supplied[task_uuid]
        label = db.get(DiseaseGrading, target.disease_grading_id)
        if not label or label.disease_id != task.disease_id:
            raise EncounterSetGradingError("A selected grade does not belong to its target.")
        if not _snapshot_allows_label(package, task.disease_id, label.id):
            raise EncounterSetGradingError(
                "A selected grade was not part of this package's frozen grading scheme."
            )
        labels_by_task_uuid[task_uuid] = label

    _claim_role(package, submission.role_slot, submission.grader_user_id)

    prior = _first_submission(
        package, submission.role_slot, submission.grader_user_id
    )
    event = EncounterSetGradingSubmission(
        package=package,
        grader_user_id=submission.grader_user_id,
        role_slot=submission.role_slot,
        submission_kind="revision" if prior else "initial",
        package_revision=package.revision_number + 1,
        is_complete=True,
        source="native",
    )
    db.add(event)
    db.flush()

    now = utcnow()
    for task_uuid, task in editable_by_uuid.items():
        target = supplied[task_uuid]
        label = labels_by_task_uuid[task_uuid]
        grade = next(
            (
                item
                for item in task.grades
                if item.grader_user_id == submission.grader_user_id
                and item.role_slot == submission.role_slot
            ),
            None,
        )
        if grade is None:
            grade = Grade(
                task_id=task.id,
                grader_user_id=submission.grader_user_id,
                role_slot=submission.role_slot,
                created_at=now,
            )
            db.add(grade)
            task.grades.append(grade)
        grade.disease_grading_id = label.id
        grade.comment = target.comment
        grade.selected_features_json = target.selected_features_json
        grade.feature_geometry_json = target.feature_geometry_json
        grade.updated_at = now
        grade.disease_name = task.disease.name if task.disease else None
        grade.grade_name = label.impression
        grade.grade_description = label.guidelines
        db.flush()
        scope = task.encounter_set_scope
        event.items.append(
            EncounterSetGradingSubmissionItem(
                encounter_set_scope_id=scope.id if scope else None,
                task_id=task.id,
                grade_id=grade.id,
                target_level=task.grading_target_level,
                scope_kind=_scope_kind(package),
                scope_disease_id=scope.scope_disease_id if scope else None,
                scope_disease_name=_scope_disease_name(package, scope),
                disease_grading_id=label.id,
                grade_name=label.impression,
                comment=target.comment,
                selected_features_json=target.selected_features_json,
                feature_geometry_json=target.feature_geometry_json,
                target_snapshot_json={
                    "task_uuid": task.uuid,
                    "disease_id": task.disease_id,
                    "disease_name": task.disease.name if task.disease else None,
                    "target_level": task.grading_target_level,
                },
            )
        )

    package.revision_number += 1
    _recompute_package(db, package)
    return event


def reconcile_package_state(db, package: EncounterSetGradingPackage, *, now=None) -> bool:
    """Lazily release expired set mismatches to masked arbitration queues."""
    if not package.scopes or any(
        len(
            [
                task
                for task in scope.tasks
                if task.grading_target_level == "encounter"
            ]
        )
        != 1
        for scope in package.scopes
    ):
        return False
    before = _package_state_signature(package)
    _recompute_package(db, package, now=now)
    changed = before != _package_state_signature(package)
    if changed:
        package.revision_number += 1
    return changed


def reconcile_active_packages(db, *, now=None) -> int:
    """Reconcile packages whose post-Resident2 waiting period may have changed."""
    packages = (
        db.query(EncounterSetGradingPackage)
        .filter(
            EncounterSetGradingPackage.state.in_(("resident2_done", "arbitration"))
        )
        .order_by(EncounterSetGradingPackage.id)
        .with_for_update(skip_locked=True)
        .all()
    )
    return sum(
        1 for package in packages if reconcile_package_state(db, package, now=now)
    )


def package_record_dto(
    package: EncounterSetGradingPackage,
    *,
    viewer_user_id: int | None = None,
) -> dict[str, Any]:
    """Serialize history exclusively from the frozen runtime record.

    A non-final record requested by a grader is masked to that grader's own
    observations. This keeps arbitration independent when the record API is
    called directly instead of through the grading workbench.
    """
    mask_incomplete = viewer_user_id is not None and package.state != "final"

    def visible_event(event: EncounterSetGradingSubmission) -> bool:
        return not mask_incomplete or event.grader_user_id == viewer_user_id

    def visible_owner(owner_id: int | None) -> int | None:
        if not mask_incomplete or owner_id == viewer_user_id:
            return owner_id
        return None

    return {
        "uuid": package.uuid,
        "encounter_uuid": package.patient_encounter.uuid,
        "name": package.name,
        "code": package.code,
        "encounter_set_type_id": package.encounter_set_type_id,
        "encounter_set_type": (
            (package.policy_snapshot_json or {}).get("encounter_set_type")
        ),
        "grading_mode": package.grading_mode,
        "state": package.state,
        "record_origin": package.record_origin,
        "policy_schema_version": package.policy_schema_version,
        "policy_revision": package.policy_revision,
        "policy_snapshot": package.policy_snapshot_json,
        "revision_number": package.revision_number,
        "role_owners": {
            "resident": visible_owner(package.resident_user_id),
            "resident2": visible_owner(package.resident2_user_id),
            "arbitrator": visible_owner(package.arbitrator_user_id),
        },
        "scopes": [
            {
                "uuid": scope.uuid,
                "scope_kind": _scope_kind(package),
                "scope_disease_id": scope.scope_disease_id,
                "scope_disease_name": _scope_disease_name(package, scope),
                "link_role": scope.link_role,
                "state": scope.state,
                "snapshot": scope.scope_snapshot_json,
                "tasks": [
                    _task_record(
                        task,
                        viewer_user_id=viewer_user_id if mask_incomplete else None,
                    )
                    for task in scope.tasks
                ],
            }
            for scope in package.scopes
        ],
        "unscoped_tasks": [
            _task_record(
                task,
                viewer_user_id=viewer_user_id if mask_incomplete else None,
            )
            for task in package.tasks
            if task.encounter_set_scope_id is None
        ],
        "submissions": [
            {
                "uuid": event.uuid,
                "role_slot": event.role_slot,
                "grader_user_id": event.grader_user_id,
                "submission_kind": event.submission_kind,
                "package_revision": event.package_revision,
                "created_at": event.created_at.isoformat(),
                "items": [
                    {
                        "task_id": item.task_id,
                        "target_level": item.target_level,
                        "scope_kind": item.scope_kind,
                        "scope_disease_id": item.scope_disease_id,
                        "scope_disease_name": item.scope_disease_name,
                        "disease_grading_id": item.disease_grading_id,
                        "grade_name": item.grade_name,
                        "comment": item.comment,
                        "selected_features_json": item.selected_features_json,
                        "feature_geometry_json": item.feature_geometry_json,
                        "target_snapshot": item.target_snapshot_json,
                    }
                    for item in event.items
                ],
            }
            for event in sorted(package.submissions, key=lambda item: item.created_at)
            if visible_event(event)
        ],
    }


def _recompute_package(db, package: EncounterSetGradingPackage, *, now=None) -> None:
    now = now or utcnow()
    resident_submission = complete_package_submission(package, "resident")
    resident2_submission = complete_package_submission(package, "resident2")
    arbitrator_submission = complete_package_submission(package, "arbitrator")
    arbitration_ready = bool(
        resident2_submission
        and now >= resident2_submission.created_at + REVISION_WINDOW
    )
    for scope in package.scopes:
        set_tasks = [
            task for task in scope.tasks if task.grading_target_level == "encounter"
        ]
        if len(set_tasks) != 1:
            raise EncounterSetGradingError(
                "Every runtime scope must contain exactly one set-level target."
            )
        set_task = set_tasks[0]
        resident = (
            _role_grade(set_task, "resident", resident_submission.grader_user_id)
            if resident_submission else None
        )
        resident2 = (
            _role_grade(set_task, "resident2", resident2_submission.grader_user_id)
            if resident2_submission else None
        )
        arbitrator = (
            _role_grade(set_task, "arbitrator", arbitrator_submission.grader_user_id)
            if arbitrator_submission else None
        )
        if arbitrator:
            _upsert_consensus(db, package, scope, set_task, arbitrator, "adjudication")
            scope.state = "final"
        elif resident and resident2 and not arbitration_ready:
            _remove_consensus(db, set_task)
            scope.state = "resident2_done"
        elif resident and resident2 and resident.disease_grading_id == resident2.disease_grading_id:
            _upsert_consensus(db, package, scope, set_task, resident2, "match")
            scope.state = "final"
        elif resident and resident2:
            _remove_consensus(db, set_task)
            scope.state = "arbitration"
        elif resident:
            scope.state = "resident_done"
        else:
            scope.state = "pending"
        for task in scope.tasks:
            task.state = scope.state

    states = {scope.state for scope in package.scopes}
    if states == {"final"}:
        if package.state != "final" or package.completed_at is None:
            package.completed_at = now
        package.state = "final"
    elif "arbitration" in states:
        package.state = "arbitration"
        package.completed_at = None
    elif states.issubset({"resident_done", "resident2_done", "final"}):
        if "resident2_done" in states:
            package.state = "resident2_done"
        else:
            package.state = "resident_done"
        package.completed_at = None
    else:
        package.state = "pending"
        package.completed_at = None


def _upsert_consensus(db, package, scope, task, grade, method: str) -> None:
    consensus = task.consensus
    decision_changed = bool(
        consensus is None
        or consensus.method != method
        or consensus.final_disease_grading_id != grade.disease_grading_id
    )
    if consensus is None:
        consensus = Consensus(task_id=task.id)
        db.add(consensus)
        task.consensus = consensus
    consensus.final_disease_grading_id = grade.disease_grading_id
    consensus.method = method
    consensus.consensus_scope = _scope_kind(package)
    consensus.encounter_set_package_id = package.id
    consensus.encounter_set_scope_id = scope.id
    consensus.scope_disease_id = scope.scope_disease_id
    consensus.scope_disease_name = _scope_disease_name(package, scope)
    consensus.decided_by_user_id = grade.grader_user_id if method == "adjudication" else None
    if decision_changed:
        consensus.decided_at = utcnow()
    consensus.final_disease_name = grade.disease_name
    consensus.final_grade_name = grade.grade_name
    consensus.final_grade_description = grade.grade_description


def _validate_role_owner(package, role_slot: str, user_id: int) -> None:
    attribute = f"{role_slot}_user_id"
    owner_id = getattr(package, attribute)
    if owner_id is not None and owner_id != user_id:
        raise EncounterSetGradingError(
            "This package role slot is already owned by another grader."
        )
    conflicting_owners = {
        slot: getattr(package, f"{slot}_user_id")
        for slot in HUMAN_ROLE_SLOTS - {role_slot}
    }
    if user_id in conflicting_owners.values():
        raise EncounterSetGradingError(
            "One person cannot occupy multiple EncounterSet grading slots."
        )


def _claim_role(package, role_slot: str, user_id: int) -> None:
    _validate_role_owner(package, role_slot, user_id)
    setattr(package, f"{role_slot}_user_id", user_id)


def _snapshot_allows_label(package, disease_id: int, label_id: int) -> bool:
    definitions = (package.policy_snapshot_json or {}).get("grading_definitions", {})
    definition = definitions.get(str(disease_id)) or {}
    return label_id in {item.get("id") for item in definition.get("labels", [])}


def _first_submission(package, role_slot: str, user_id: int):
    return min(
        (
            event
            for event in package.submissions
            if event.role_slot == role_slot
            and event.grader_user_id == user_id
            and event.is_complete
        ),
        key=lambda event: event.created_at,
        default=None,
    )


def _role_grade(task, role_slot: str, owner_id: int | None):
    return next(
        (
            grade
            for grade in task.grades
            if grade.role_slot == role_slot
            and (owner_id is None or grade.grader_user_id == owner_id)
        ),
        None,
    )


def _scope_has_adjudication(scope) -> bool:
    return any(
        task.consensus and task.consensus.method == "adjudication"
        for task in scope.tasks
        if task.grading_target_level == "encounter"
    )


def _remove_consensus(db, task: GradingTask) -> None:
    if task.consensus is not None:
        db.delete(task.consensus)
        task.consensus = None


def _package_state_signature(package: EncounterSetGradingPackage) -> tuple:
    return (
        package.state,
        package.completed_at,
        tuple(
            (
                scope.id,
                scope.state,
                tuple(
                    (
                        task.id,
                        task.state,
                        task.consensus.method if task.consensus else None,
                        (
                            task.consensus.final_disease_grading_id
                            if task.consensus
                            else None
                        ),
                    )
                    for task in scope.tasks
                ),
            )
            for scope in package.scopes
        ),
    )


def _scope_kind(package) -> str:
    return (
        "encounter_set_unified"
        if package.grading_mode == "unified"
        else "encounter_set_disease"
    )


def _scope_disease_name(package, scope) -> str | None:
    if scope is None or scope.scope_disease_id is None:
        return None
    definitions = (package.policy_snapshot_json or {}).get("grading_definitions", {})
    return (definitions.get(str(scope.scope_disease_id)) or {}).get("name")


def _task_record(
    task: GradingTask,
    *,
    viewer_user_id: int | None = None,
) -> dict[str, Any]:
    return {
        "uuid": task.uuid,
        "target_level": task.grading_target_level,
        "disease_id": task.disease_id,
        "image_uuid": task.encounter_set_image.uuid if task.encounter_set_image else None,
        "grades": [
            {
                "role_slot": grade.role_slot,
                "grader_user_id": grade.grader_user_id,
                "disease_grading_id": grade.disease_grading_id,
                "disease_name": grade.disease_name,
                "grade_name": grade.grade_name,
                "grade_description": grade.grade_description,
                "comment": grade.comment,
                "selected_features_json": grade.selected_features_json,
                "feature_geometry_json": grade.feature_geometry_json,
                "created_at": grade.created_at.isoformat(),
                "updated_at": grade.updated_at.isoformat(),
            }
            for grade in task.grades
            if viewer_user_id is None or grade.grader_user_id == viewer_user_id
        ],
        "consensus": (
            {
                "method": task.consensus.method,
                "scope": task.consensus.consensus_scope,
                "scope_disease_id": task.consensus.scope_disease_id,
                "scope_disease_name": task.consensus.scope_disease_name,
                "final_disease_grading_id": task.consensus.final_disease_grading_id,
                "final_grade_name": task.consensus.final_grade_name,
                "decided_at": task.consensus.decided_at.isoformat(),
            }
            if task.consensus and viewer_user_id is None
            else None
        ),
    }
