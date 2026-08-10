"""One-time bounded backfill of negative controls for verified positive sets.

Preview is read-only. Validation executes the exact plan then rolls it back.
Apply requires the confirmation token emitted by a fresh preview.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from db_transaction_manager import transaction_scope
from models import (
    Disease,
    EncounterSetGradingPackage,
    Grade,
    GradingTask,
    PatientEncounters,
)
from verify_encounter_set.routes import (
    _active_encounter_set_type_config,
    _create_negative_control_tasks_for_positive,
    _encounter_has_incompatible_runtime_package,
    _encounter_has_negative_control_tasks,
    _encounter_is_negative_for_disease,
    _encounter_is_positive_for_disease,
    _encounter_set_package_configs,
    _eligible_encounter_set_images,
)
from upload_profiles.image_task_routing import image_metadata_matches_rule


class NegativeControlBackfillError(RuntimeError):
    pass


@dataclass(frozen=True)
class Assignment:
    positive_encounter_id: int
    positive_package_id: int
    disease_id: int
    controls_per_positive: int
    candidate_encounter_ids: tuple[int, ...]


@dataclass(frozen=True)
class Plan:
    assignments: tuple[Assignment, ...]
    positive_package_count: int
    positive_encounter_count: int
    selected_control_count: int
    selected_control_counts_by_disease: dict[str, int]
    confirmation_token: str

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Result:
    selected_control_count: int
    created_record_count: int
    negative_package_count: int
    negative_set_task_count: int
    negative_image_task_count: int
    attached_ai_grade_count: int
    human_grade_count: int

    def as_dict(self):
        return asdict(self)


def _package_config(db, package, encounter):
    config = _active_encounter_set_type_config(encounter)
    matches = [
        item
        for item in _encounter_set_package_configs(db, config, encounter)
        if item["code"] == package.code
    ]
    if len(matches) != 1:
        raise NegativeControlBackfillError(
            f"Package {package.id} does not resolve exactly one current policy."
        )
    return matches[0]


def _sampling_root(config):
    sampling_ids = {
        disease_id
        for disease_id, policy in config["image_scheme_policies"].items()
        if policy == "positive_plus_negative_controls"
    }
    if config["grading_mode"] == "disease_specific":
        root = config.get("root_scope_disease_id")
        return root if root in sampling_ids else None
    return next(iter(sampling_ids)) if len(sampling_ids) == 1 else None


def _candidate_ids(db, positive, disease_id, config, reserved):
    positive_config = _active_encounter_set_type_config(positive)
    candidates = (
        db.query(PatientEncounters)
        .filter(
            PatientEncounters.id != positive.id,
            PatientEncounters.is_set_based.is_(True),
            PatientEncounters.encounter_verified_status == "verified",
            PatientEncounters.lab_unit_id == positive.lab_unit_id,
            PatientEncounters.project_id == positive.project_id,
            PatientEncounters.upload_profile_id == positive.upload_profile_id,
        )
        .order_by(PatientEncounters.id)
        .all()
    )
    eligible = []
    for candidate in candidates:
        candidate_config = _active_encounter_set_type_config(candidate)
        if (
            not candidate_config
            or not positive_config
            or candidate_config.encounter_set_type_id
            != positive_config.encounter_set_type_id
            or candidate.id in reserved
            or not _encounter_is_negative_for_disease(db, candidate, disease_id)
            or _encounter_has_incompatible_runtime_package(
                db, candidate_id=candidate.id, package_config=config
            )
            or _encounter_has_negative_control_tasks(db, candidate.id, disease_id)
        ):
            continue
        matching_images = [
            image
            for image in _eligible_encounter_set_images(db, candidate)
            if image_metadata_matches_rule(
                image.metadata_json,
                config["image_scheme_metadata_rules"].get(disease_id),
            )
        ]
        if matching_images:
            eligible.append(candidate.id)
    return eligible


def build_plan(db, *, lock=False):
    existing_negative_task_count = (
        db.query(GradingTask)
        .filter(GradingTask.task_source == "profile_package_negative_control")
        .count()
    )
    if existing_negative_task_count:
        raise NegativeControlBackfillError(
            "Negative-control tasks already exist; this one-time backfill refuses "
            "to resample them."
        )
    package_stmt = (
        select(EncounterSetGradingPackage.id)
        .where(
            EncounterSetGradingPackage.state == "pending",
            EncounterSetGradingPackage.record_origin == "native",
        )
        .order_by(EncounterSetGradingPackage.id)
    )
    if lock:
        package_stmt = package_stmt.with_for_update()
    package_ids = tuple(db.execute(package_stmt).scalars())
    packages = [db.get(EncounterSetGradingPackage, value) for value in package_ids]
    positive_rows = []
    for package in packages:
        encounter = db.get(PatientEncounters, package.patient_encounter_id)
        config = _package_config(db, package, encounter)
        disease_id = _sampling_root(config)
        if disease_id is None or not _encounter_is_positive_for_disease(
            db, encounter, disease_id
        ):
            continue
        ratio = int(
            config["image_scheme_negative_controls_per_positive"].get(
                disease_id, 0
            )
        )
        if ratio > 0:
            positive_rows.append((package, encounter, config, disease_id, ratio))

    assignments = []
    reserved_by_disease = {}
    disease_names = {}
    for package, encounter, config, disease_id, ratio in positive_rows:
        reserved = reserved_by_disease.setdefault(disease_id, set())
        candidates = _candidate_ids(
            db, encounter, disease_id, config, reserved
        )
        ranked = sorted(
            candidates,
            key=lambda candidate_id: sha256(
                f"{package.id}:{disease_id}:{candidate_id}".encode("ascii")
            ).hexdigest(),
        )
        selected = tuple(ranked[:ratio])
        reserved.update(selected)
        disease_names[disease_id] = db.get(Disease, disease_id).name
        assignments.append(
            Assignment(
                positive_encounter_id=encounter.id,
                positive_package_id=package.id,
                disease_id=disease_id,
                controls_per_positive=ratio,
                candidate_encounter_ids=selected,
            )
        )

    digest_source = json.dumps(
        [asdict(item) for item in assignments], sort_keys=True
    ).encode("utf-8")
    digest = sha256(digest_source).hexdigest()[:12].upper()
    counts = {}
    for item in assignments:
        name = disease_names[item.disease_id]
        counts[name] = counts.get(name, 0) + len(item.candidate_encounter_ids)
    selected_count = sum(len(item.candidate_encounter_ids) for item in assignments)
    return Plan(
        assignments=tuple(assignments),
        positive_package_count=len(assignments),
        positive_encounter_count=len(
            {item.positive_encounter_id for item in assignments}
        ),
        selected_control_count=selected_count,
        selected_control_counts_by_disease=counts,
        confirmation_token=(
            f"BACKFILL-{len(assignments)}-POS-{selected_count}-CONTROLS-{digest}"
        ),
    )


def apply_plan(db, token):
    plan = build_plan(db, lock=True)
    if token != plan.confirmation_token:
        raise NegativeControlBackfillError(
            "Confirmation token does not match the locked plan. "
            f"Expected {plan.confirmation_token}."
        )
    before_package_ids = set(
        db.execute(select(EncounterSetGradingPackage.id)).scalars()
    )
    created = 0
    for assignment in plan.assignments:
        if not assignment.candidate_encounter_ids:
            continue
        package = db.get(
            EncounterSetGradingPackage, assignment.positive_package_id
        )
        positive = db.get(PatientEncounters, assignment.positive_encounter_id)
        config = _package_config(db, package, positive)
        created += _create_negative_control_tasks_for_positive(
            db,
            positive_encounter=positive,
            disease_id=assignment.disease_id,
            package_config=config,
            controls_per_positive=len(assignment.candidate_encounter_ids),
            candidate_encounter_ids=assignment.candidate_encounter_ids,
        )
    db.flush()
    after_package_ids = set(
        db.execute(select(EncounterSetGradingPackage.id)).scalars()
    )
    new_package_ids = after_package_ids - before_package_ids
    tasks = (
        db.query(GradingTask)
        .filter(GradingTask.encounter_set_package_id.in_(new_package_ids))
        .all()
        if new_package_ids
        else []
    )
    for task in tasks:
        task.state = "pending"
    db.flush()
    if len(new_package_ids) != plan.selected_control_count:
        raise NegativeControlBackfillError(
            "Not every selected control produced exactly one package; rolling back."
        )
    if any(
        task.task_source != "profile_package_negative_control" for task in tasks
    ):
        raise NegativeControlBackfillError(
            "A backfilled task has unexpected provenance; rolling back."
        )
    return Result(
        selected_control_count=plan.selected_control_count,
        created_record_count=created,
        negative_package_count=len(new_package_ids),
        negative_set_task_count=sum(
            task.grading_target_level == "encounter" for task in tasks
        ),
        negative_image_task_count=sum(
            task.grading_target_level == "image" for task in tasks
        ),
        attached_ai_grade_count=(
            db.query(Grade)
            .filter(Grade.task_id.in_([task.id for task in tasks]), Grade.role_slot == "ai")
            .count()
        ),
        human_grade_count=(
            db.query(Grade)
            .filter(Grade.task_id.in_([task.id for task in tasks]), Grade.role_slot != "ai")
            .count()
        ),
    )


class _Rollback(Exception):
    def __init__(self, result):
        self.result = result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--validate-apply", action="store_true")
    parser.add_argument("--confirm-token")
    args = parser.parse_args()
    if (args.apply or args.validate_apply) != bool(args.confirm_token):
        parser.error("apply modes require --confirm-token; preview does not accept it")

    if not (args.apply or args.validate_apply):
        with transaction_scope() as db:
            print(json.dumps({"mode": "preview", **build_plan(db).as_dict()}, indent=2))
        return 0
    try:
        with transaction_scope() as db:
            result = apply_plan(db, args.confirm_token)
            if args.validate_apply:
                raise _Rollback(result)
            print(json.dumps({"mode": "apply", **result.as_dict()}, indent=2))
    except _Rollback as rollback:
        print(
            json.dumps(
                {
                    "mode": "validate_apply_rolled_back",
                    **rollback.result.as_dict(),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
