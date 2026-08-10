"""Frozen EncounterSet grading record DTOs and package workflow rules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
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


REVISION_WINDOW = timedelta(hours=12)
HUMAN_ROLE_SLOTS = {"resident", "resident2", "arbitrator"}


class EncounterSetGradingError(ValueError):
    pass


class StaleEncounterSetPackageError(EncounterSetGradingError):
    pass


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
    package: EncounterSetGradingPackage, role_slot: str, grader_user_id: int
) -> list[GradingTask]:
    if role_slot not in HUMAN_ROLE_SLOTS:
        return []
    now = utcnow()
    first_submission = _first_submission(package, role_slot, grader_user_id)
    within_revision = bool(
        first_submission and now <= first_submission.created_at + REVISION_WINDOW
    )
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
            if role_slot == "resident2" and not _scope_has_role_grade(
                scope, "resident"
            ):
                continue
        result.extend(scope.tasks)
    return result


def submit_package(
    db, package: EncounterSetGradingPackage, submission: EncounterSetSubmissionInputDTO
) -> EncounterSetGradingSubmission:
    if submission.role_slot not in HUMAN_ROLE_SLOTS:
        raise EncounterSetGradingError("Invalid package role slot.")
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


def _recompute_package(db, package: EncounterSetGradingPackage) -> None:
    for scope in package.scopes:
        set_tasks = [
            task for task in scope.tasks if task.grading_target_level == "encounter"
        ]
        if len(set_tasks) != 1:
            raise EncounterSetGradingError(
                "Every runtime scope must contain exactly one set-level target."
            )
        set_task = set_tasks[0]
        resident = _role_grade(set_task, "resident", package.resident_user_id)
        resident2 = _role_grade(set_task, "resident2", package.resident2_user_id)
        arbitrator = _role_grade(set_task, "arbitrator", package.arbitrator_user_id)
        if arbitrator:
            _upsert_consensus(db, package, scope, set_task, arbitrator, "adjudication")
            scope.state = "final"
        elif resident and resident2 and resident.disease_grading_id == resident2.disease_grading_id:
            _upsert_consensus(db, package, scope, set_task, resident2, "match")
            scope.state = "final"
        elif resident and resident2:
            if set_task.consensus:
                db.delete(set_task.consensus)
                set_task.consensus = None
            scope.state = "arbitration"
        elif resident:
            scope.state = "resident_done"
        else:
            scope.state = "pending"
        for task in scope.tasks:
            task.state = scope.state

    states = {scope.state for scope in package.scopes}
    if states == {"final"}:
        package.state = "final"
        package.completed_at = utcnow()
    elif "arbitration" in states:
        package.state = "arbitration"
        package.completed_at = None
    elif states.issubset({"resident_done", "final"}):
        package.state = "resident_done"
        package.completed_at = None
    else:
        package.state = "pending"
        package.completed_at = None


def _upsert_consensus(db, package, scope, task, grade, method: str) -> None:
    consensus = task.consensus
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
    if role_slot == "resident" and package.resident2_user_id == user_id:
        raise EncounterSetGradingError("One person cannot occupy both resident slots.")
    if role_slot == "resident2" and package.resident_user_id == user_id:
        raise EncounterSetGradingError("One person cannot occupy both resident slots.")


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
            if event.role_slot == role_slot and event.grader_user_id == user_id
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


def _scope_has_role_grade(scope, role_slot: str) -> bool:
    return any(
        grade.role_slot == role_slot for task in scope.tasks for grade in task.grades
    )


def _scope_has_adjudication(scope) -> bool:
    return any(
        task.consensus and task.consensus.method == "adjudication"
        for task in scope.tasks
        if task.grading_target_level == "encounter"
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
