"""Transactional repair of legacy EncounterSet grading packages.

This module deliberately knows nothing about Flask routes. Callers provide the
current-policy resolver and task creator so the destructive part remains a
small, testable domain operation with an explicit preview/apply contract.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Callable, Iterable

from sqlalchemy import delete, func, select, update

from models import (
    Consensus,
    Disease,
    EncounterSetGradingPackage,
    EncounterSetGradingSubmission,
    Grade,
    GradingTask,
    PatientEncounters,
)


PolicyResolver = Callable[[Any, PatientEncounters], Iterable[dict[str, Any]]]
TaskCreator = Callable[[Any, PatientEncounters, frozenset[int]], int]


class EncounterSetPackageRepairError(RuntimeError):
    """Raised when preview/apply safety conditions are not satisfied."""


@dataclass(frozen=True)
class EncounterPolicyPreviewDTO:
    encounter_id: int
    encounter_uuid: str
    project_id: int | None
    package_codes: tuple[str, ...]


@dataclass(frozen=True)
class EncounterSetPackageRepairPreviewDTO:
    package_ids: tuple[int, ...]
    set_package_ids: tuple[int, ...]
    supplemental_empty_package_ids: tuple[int, ...]
    encounter_ids: tuple[int, ...]
    task_ids: tuple[int, ...]
    ai_task_ids: tuple[int, ...]
    ai_grade_ids: tuple[int, ...]
    set_task_count: int
    package_count: int
    encounter_count: int
    image_task_count: int
    ai_task_count: int
    ai_grade_count: int
    non_ai_grade_count: int
    set_grade_count: int
    submission_count: int
    consensus_count: int
    grade_counts: dict[str, int]
    package_state_counts: dict[str, int]
    policies: tuple[EncounterPolicyPreviewDTO, ...]
    confirmation_token: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EncounterSetPackageRepairResultDTO:
    removed_package_count: int
    removed_task_count: int
    removed_non_ai_grade_count: int
    preserved_ai_task_count: int
    preserved_ai_grade_count: int
    rebuilt_encounter_count: int
    created_record_count: int
    resulting_package_count: int
    resulting_scope_count: int
    resulting_set_task_count: int
    resulting_image_task_count: int
    encounters_with_packages_count: int
    resulting_package_counts_by_project: dict[str, int]
    resulting_task_counts_by_disease_and_target: dict[str, int]
    attached_preserved_ai_task_count: int
    unscoped_preserved_ai_task_count: int
    unscoped_ai_task_counts_by_disease: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def preview_set_package_rebuild(
    db,
    *,
    policy_resolver: PolicyResolver,
    lock: bool = False,
) -> EncounterSetPackageRepairPreviewDTO:
    """Preview packages containing set-level tasks and their current policies."""
    package_id_stmt = (
        select(GradingTask.encounter_set_package_id)
        .where(
            GradingTask.grading_target_level == "encounter",
            GradingTask.encounter_set_package_id.is_not(None),
        )
        .distinct()
        .order_by(GradingTask.encounter_set_package_id)
    )
    set_package_ids = tuple(db.execute(package_id_stmt).scalars())
    if not set_package_ids:
        raise EncounterSetPackageRepairError(
            "No package-owned EncounterSet set-level tasks were found."
        )

    target_package_rows = db.execute(
        select(
            EncounterSetGradingPackage.id,
            EncounterSetGradingPackage.patient_encounter_id,
        ).where(EncounterSetGradingPackage.id.in_(set_package_ids))
    ).all()
    encounter_ids = tuple(
        sorted({row.patient_encounter_id for row in target_package_rows})
    )
    package_ids = tuple(
        db.execute(
            select(EncounterSetGradingPackage.id)
            .where(
                EncounterSetGradingPackage.patient_encounter_id.in_(encounter_ids)
            )
            .order_by(EncounterSetGradingPackage.id)
        ).scalars()
    )
    supplemental_package_ids = tuple(
        package_id for package_id in package_ids if package_id not in set_package_ids
    )

    lock_stmt = (
        select(EncounterSetGradingPackage.id)
        .where(EncounterSetGradingPackage.id.in_(package_ids))
        .order_by(EncounterSetGradingPackage.id)
    )
    if lock:
        lock_stmt = lock_stmt.with_for_update()
    locked_package_ids = tuple(db.execute(lock_stmt).scalars())
    if locked_package_ids != package_ids:
        raise EncounterSetPackageRepairError(
            "The package population changed while the rebuild was being prepared."
        )
    current_set_package_ids = tuple(db.execute(package_id_stmt).scalars())
    current_package_ids = tuple(
        db.execute(
            select(EncounterSetGradingPackage.id)
            .where(
                EncounterSetGradingPackage.patient_encounter_id.in_(encounter_ids)
            )
            .order_by(EncounterSetGradingPackage.id)
        ).scalars()
    )
    if (
        current_set_package_ids != set_package_ids
        or current_package_ids != package_ids
    ):
        raise EncounterSetPackageRepairError(
            "The package population changed while locks were being acquired."
        )

    task_stmt = (
        select(
            GradingTask.id,
            GradingTask.grading_target_level,
            GradingTask.encounter_set_image_id,
            GradingTask.disease_id,
        )
        .where(GradingTask.encounter_set_package_id.in_(package_ids))
        .order_by(GradingTask.id)
    )
    if lock:
        task_stmt = task_stmt.with_for_update()
    task_rows = db.execute(task_stmt).all()
    task_ids = tuple(row.id for row in task_rows)
    supplemental_task_count = (
        db.query(GradingTask)
        .filter(GradingTask.encounter_set_package_id.in_(supplemental_package_ids))
        .count()
        if supplemental_package_ids
        else 0
    )
    if supplemental_task_count:
        raise EncounterSetPackageRepairError(
            "A package without a set-level task on an affected EncounterSet contains "
            "other tasks; its history requires separate review."
        )

    grade_stmt = (
        select(Grade.id, Grade.task_id, Grade.role_slot)
        .where(Grade.task_id.in_(task_ids))
        .order_by(Grade.id)
    )
    if lock:
        grade_stmt = grade_stmt.with_for_update()
    grade_rows = db.execute(grade_stmt).all() if task_ids else []
    grade_counts = Counter(row.role_slot for row in grade_rows)
    ai_grade_ids = tuple(row.id for row in grade_rows if row.role_slot == "ai")
    ai_task_ids = tuple(sorted({row.task_id for row in grade_rows if row.role_slot == "ai"}))

    task_by_id = {row.id: row for row in task_rows}
    ai_identities: set[tuple[int, int]] = set()
    for task_id in ai_task_ids:
        row = task_by_id[task_id]
        if row.grading_target_level != "image" or row.encounter_set_image_id is None:
            raise EncounterSetPackageRepairError(
                f"AI grade task {task_id} is not an EncounterSet image target."
            )
        identity = (row.encounter_set_image_id, row.disease_id)
        if identity in ai_identities:
            raise EncounterSetPackageRepairError(
                "AI observations contain duplicate image/disease tasks that cannot "
                "be safely detached from their legacy packages."
            )
        ai_identities.add(identity)

    package_rows = db.execute(
        select(
            EncounterSetGradingPackage.patient_encounter_id,
            EncounterSetGradingPackage.state,
        ).where(EncounterSetGradingPackage.id.in_(package_ids))
    ).all()
    encounters = list(
        db.execute(
            select(PatientEncounters)
            .where(PatientEncounters.id.in_(encounter_ids))
            .order_by(PatientEncounters.id)
        ).scalars()
    )
    if len(encounters) != len(encounter_ids):
        raise EncounterSetPackageRepairError(
            "One or more package EncounterSets no longer exist."
        )

    policies: list[EncounterPolicyPreviewDTO] = []
    for encounter in encounters:
        package_configs = tuple(policy_resolver(db, encounter))
        package_codes = tuple(str(config["code"]) for config in package_configs)
        if not package_codes:
            raise EncounterSetPackageRepairError(
                f"EncounterSet {encounter.uuid} has no current grading package policy."
            )
        if len(set(package_codes)) != len(package_codes):
            raise EncounterSetPackageRepairError(
                f"EncounterSet {encounter.uuid} resolves duplicate current package codes."
            )
        policies.append(
            EncounterPolicyPreviewDTO(
                encounter_id=encounter.id,
                encounter_uuid=encounter.uuid,
                project_id=encounter.project_id,
                package_codes=package_codes,
            )
        )

    submission_count = db.query(EncounterSetGradingSubmission).filter(
        EncounterSetGradingSubmission.encounter_set_package_id.in_(package_ids)
    ).count()
    consensus_count = db.query(Consensus).filter(Consensus.task_id.in_(task_ids)).count()
    set_task_count = sum(
        row.grading_target_level == "encounter" for row in task_rows
    )
    set_grade_count = sum(
        task_by_id[row.task_id].grading_target_level == "encounter"
        for row in grade_rows
    )
    digest_material = ",".join(
        str(value)
        for value in (*package_ids, *task_ids, *ai_grade_ids)
    ).encode("ascii")
    digest = sha256(digest_material).hexdigest()[:12].upper()
    confirmation_token = (
        f"REBUILD-{set_task_count}-SET-{len(encounter_ids)}-ENC-"
        f"PRESERVE-{len(ai_grade_ids)}-AI-{digest}"
    )

    return EncounterSetPackageRepairPreviewDTO(
        package_ids=package_ids,
        set_package_ids=set_package_ids,
        supplemental_empty_package_ids=supplemental_package_ids,
        encounter_ids=encounter_ids,
        task_ids=task_ids,
        ai_task_ids=ai_task_ids,
        ai_grade_ids=ai_grade_ids,
        set_task_count=set_task_count,
        package_count=len(set_package_ids),
        encounter_count=len(encounter_ids),
        image_task_count=sum(row.grading_target_level == "image" for row in task_rows),
        ai_task_count=len(ai_task_ids),
        ai_grade_count=len(ai_grade_ids),
        non_ai_grade_count=len(grade_rows) - len(ai_grade_ids),
        set_grade_count=set_grade_count,
        submission_count=submission_count,
        consensus_count=consensus_count,
        grade_counts=dict(sorted(grade_counts.items())),
        package_state_counts=dict(
            sorted(Counter(row.state for row in package_rows).items())
        ),
        policies=tuple(policies),
        confirmation_token=confirmation_token,
    )


def apply_set_package_rebuild(
    db,
    *,
    confirmation_token: str,
    policy_resolver: PolicyResolver,
    task_creator: TaskCreator,
) -> EncounterSetPackageRepairResultDTO:
    """Discard human history, preserve AI observations, and rebuild current tasks."""
    preview = preview_set_package_rebuild(
        db, policy_resolver=policy_resolver, lock=True
    )
    if confirmation_token != preview.confirmation_token:
        raise EncounterSetPackageRepairError(
            "Confirmation token does not match the locked rebuild population. "
            f"Run preview again; expected {preview.confirmation_token}."
        )
    if preview.submission_count or preview.consensus_count:
        raise EncounterSetPackageRepairError(
            "Refusing to rebuild packages with immutable submissions or consensus rows."
        )
    unsupported_roles = set(preview.grade_counts) - {"resident", "ai"}
    if unsupported_roles:
        raise EncounterSetPackageRepairError(
            "Refusing to discard unexpected grade role slots: "
            + ", ".join(sorted(unsupported_roles))
        )

    task_ids = preview.task_ids
    preserved_task_ids = frozenset(preview.ai_task_ids)
    removable_task_ids = tuple(
        task_id for task_id in task_ids if task_id not in preserved_task_ids
    )

    removed_grade_result = db.execute(
        delete(Grade).where(
            Grade.task_id.in_(task_ids),
            Grade.role_slot != "ai",
        )
    )
    if preserved_task_ids:
        db.execute(
            update(GradingTask)
            .where(GradingTask.id.in_(preserved_task_ids))
            .values(
                encounter_set_package_id=None,
                encounter_set_scope_id=None,
                state="pending",
            )
        )
    if removable_task_ids:
        db.execute(delete(GradingTask).where(GradingTask.id.in_(removable_task_ids)))
    removed_package_result = db.execute(
        delete(EncounterSetGradingPackage).where(
            EncounterSetGradingPackage.id.in_(preview.package_ids)
        )
    )
    db.flush()
    db.expire_all()

    encounters = list(
        db.execute(
            select(PatientEncounters)
            .where(PatientEncounters.id.in_(preview.encounter_ids))
            .order_by(PatientEncounters.id)
        ).scalars()
    )
    created_record_count = sum(
        task_creator(db, encounter, preserved_task_ids) for encounter in encounters
    )
    db.flush()
    if preserved_task_ids:
        db.execute(
            update(GradingTask)
            .where(
                GradingTask.id.in_(preserved_task_ids),
                GradingTask.encounter_set_package_id.is_(None),
            )
            .values(state="final")
        )
        db.flush()

    preserved_grade_ids = tuple(
        db.execute(
            select(Grade.id)
            .where(Grade.id.in_(preview.ai_grade_ids), Grade.role_slot == "ai")
            .order_by(Grade.id)
        ).scalars()
    )
    if preserved_grade_ids != preview.ai_grade_ids:
        raise EncounterSetPackageRepairError(
            "AI grade preservation check failed; rolling back the rebuild."
        )
    rebuilt_packages = (
        db.query(EncounterSetGradingPackage)
        .filter(
            EncounterSetGradingPackage.patient_encounter_id.in_(
                preview.encounter_ids
            )
        )
        .all()
    )
    for package in rebuilt_packages:
        if (
            package.state != "pending"
            or package.resident_user_id is not None
            or package.resident2_user_id is not None
            or package.arbitrator_user_id is not None
        ):
            raise EncounterSetPackageRepairError(
                "A rebuilt package is not in an unclaimed pending state; rolling back."
            )
        if not package.scopes:
            raise EncounterSetPackageRepairError(
                "A rebuilt package has no frozen grading scopes; rolling back."
            )
        for scope in package.scopes:
            set_targets = [
                task
                for task in scope.tasks
                if task.grading_target_level == "encounter"
            ]
            if scope.state != "pending" or len(set_targets) != 1:
                raise EncounterSetPackageRepairError(
                    "Every rebuilt scope must be pending with exactly one set target; "
                    "rolling back."
                )

    remaining_human_count = (
        db.query(Grade)
        .join(GradingTask, Grade.task_id == GradingTask.id)
        .join(
            EncounterSetGradingPackage,
            EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id,
        )
        .filter(
            EncounterSetGradingPackage.patient_encounter_id.in_(
                preview.encounter_ids
            ),
            Grade.role_slot != "ai",
        )
        .count()
    )
    if remaining_human_count:
        raise EncounterSetPackageRepairError(
            "A rebuilt package unexpectedly inherited a human grade; rolling back."
        )

    attached_ai_tasks = db.query(GradingTask).filter(
        GradingTask.id.in_(preserved_task_ids),
        GradingTask.encounter_set_package_id.is_not(None),
    ).count()
    resulting_package_ids = tuple(package.id for package in rebuilt_packages)
    resulting_tasks = (
        db.query(GradingTask)
        .filter(GradingTask.encounter_set_package_id.in_(resulting_package_ids))
        .all()
        if resulting_package_ids
        else []
    )
    resulting_scope_count = sum(len(package.scopes) for package in rebuilt_packages)
    project_package_rows = (
        db.query(PatientEncounters.project_id, func.count(EncounterSetGradingPackage.id))
        .join(
            EncounterSetGradingPackage,
            EncounterSetGradingPackage.patient_encounter_id == PatientEncounters.id,
        )
        .filter(EncounterSetGradingPackage.id.in_(resulting_package_ids))
        .group_by(PatientEncounters.project_id)
        .all()
        if resulting_package_ids
        else []
    )
    disease_target_rows = (
        db.query(
            Disease.name,
            GradingTask.grading_target_level,
            func.count(GradingTask.id),
        )
        .join(Disease, Disease.id == GradingTask.disease_id)
        .filter(GradingTask.encounter_set_package_id.in_(resulting_package_ids))
        .group_by(Disease.name, GradingTask.grading_target_level)
        .order_by(Disease.name, GradingTask.grading_target_level)
        .all()
        if resulting_package_ids
        else []
    )
    unscoped_ai_rows = (
        db.query(Disease.name, func.count(GradingTask.id))
        .join(Disease, Disease.id == GradingTask.disease_id)
        .filter(
            GradingTask.id.in_(preserved_task_ids),
            GradingTask.encounter_set_package_id.is_(None),
        )
        .group_by(Disease.name)
        .order_by(Disease.name)
        .all()
        if preserved_task_ids
        else []
    )
    return EncounterSetPackageRepairResultDTO(
        removed_package_count=removed_package_result.rowcount,
        removed_task_count=len(removable_task_ids),
        removed_non_ai_grade_count=removed_grade_result.rowcount,
        preserved_ai_task_count=len(preserved_task_ids),
        preserved_ai_grade_count=len(preserved_grade_ids),
        rebuilt_encounter_count=len(encounters),
        created_record_count=created_record_count,
        resulting_package_count=len(rebuilt_packages),
        resulting_scope_count=resulting_scope_count,
        resulting_set_task_count=sum(
            task.grading_target_level == "encounter" for task in resulting_tasks
        ),
        resulting_image_task_count=sum(
            task.grading_target_level == "image" for task in resulting_tasks
        ),
        encounters_with_packages_count=len(
            {package.patient_encounter_id for package in rebuilt_packages}
        ),
        resulting_package_counts_by_project={
            str(project_id): count for project_id, count in project_package_rows
        },
        resulting_task_counts_by_disease_and_target={
            f"{disease_name}:{target_level}": count
            for disease_name, target_level, count in disease_target_rows
        },
        attached_preserved_ai_task_count=attached_ai_tasks,
        unscoped_preserved_ai_task_count=len(preserved_task_ids) - attached_ai_tasks,
        unscoped_ai_task_counts_by_disease={
            disease_name: count for disease_name, count in unscoped_ai_rows
        },
    )
