"""Preview or apply a narrowly scoped Remidio lab-unit lineage repair.

This is a manual, one-time maintenance command.  It is never imported by
application startup, migrations, or workers.  Preview is the default:

    uv run python scripts/remidio_lab_unit_repair.py \
        --project-code ICMR-VG \
        --binding-id 14 \
        --source-lab-unit-id 3 \
        --target-lab-unit-id 1

Apply only after reviewing the JSON manifest and re-running the same command
with the exact token emitted by that preview:

    uv run python scripts/remidio_lab_unit_repair.py \
        --project-code ICMR-VG --binding-id 14 \
        --source-lab-unit-id 3 --target-lab-unit-id 1 \
        --apply --confirm-token REPAIR-RE... \
        --manifest /tmp/icmr-vg-lab-repair.json

The command is intentionally scoped by project code, binding, and both lab
IDs.  It refuses unknown or mixed lineage and performs all ORM updates in one
transaction.  It emits identifiers needed to audit the repair (database IDs
and table names only); it never emits patient names, MRNs, UUIDs, filenames,
or other clinical metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import or_

from db_transaction_manager import transaction_scope
from models import (
    EncounterFile,
    EncounterFilePDF,
    EncounterSetGradingPackage,
    EncounterSetImage,
    GradingTask,
    IntraRaterTask,
    LabUnit,
    PatientEncounters,
    Project,
    RegradeTask,
    RemidioExam,
)
from project_configuration.models import ProjectLabUnit
from remidio_api_integration.models import (
    ProjectUploadProfileRemidioApiBinding,
    RemidioApiExamEncounter,
    RemidioApiSourceRule,
)
from upload_profiles.models import ProjectUploadProfile


class RemidioLabUnitRepairError(RuntimeError):
    """Raised when the requested repair scope is absent, stale, or unsafe."""


@dataclass
class _LabRecord:
    """A lab-unit-bearing ORM row included in the closed repair scope."""

    table: str
    record_id: int
    entity: Any
    before_lab_unit_id: int | None

    def manifest_entry(self, target_lab_unit_id: int) -> dict[str, int | str | None]:
        return {
            "table": self.table,
            "id": self.record_id,
            "before_lab_unit_id": self.before_lab_unit_id,
            "after_lab_unit_id": target_lab_unit_id,
        }


@dataclass
class RepairScope:
    """Resolved, auditable scope for one manual repair run."""

    project_id: int
    project_code: str
    binding_id: int
    project_upload_profile_id: int
    source_lab_unit_id: int
    target_lab_unit_id: int
    link_ids: tuple[int, ...]
    records: list[_LabRecord]

    @property
    def encounter_ids(self) -> tuple[int, ...]:
        return tuple(record.record_id for record in self.records if record.table == "patient_encounters")

    @property
    def confirmation_token(self) -> str:
        material = {
            "project_id": self.project_id,
            "project_code": self.project_code,
            "binding_id": self.binding_id,
            "project_upload_profile_id": self.project_upload_profile_id,
            "source_lab_unit_id": self.source_lab_unit_id,
            "target_lab_unit_id": self.target_lab_unit_id,
            "link_ids": self.link_ids,
            "records": [(record.table, record.record_id) for record in self.records],
        }
        digest = hashlib.sha256(
            json.dumps(material, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16].upper()
        return f"REPAIR-REMIDIO-LAB-{digest}"

    def to_dict(self, *, applied: bool = False) -> dict[str, Any]:
        manifest = [record.manifest_entry(self.target_lab_unit_id) for record in self.records]
        changed = sum(
            record.before_lab_unit_id != self.target_lab_unit_id for record in self.records
        )
        return {
            "mode": "applied" if applied else "preview",
            "project_id": self.project_id,
            "project_code": self.project_code,
            "binding_id": self.binding_id,
            "project_upload_profile_id": self.project_upload_profile_id,
            "source_lab_unit_id": self.source_lab_unit_id,
            "target_lab_unit_id": self.target_lab_unit_id,
            "link_ids": list(self.link_ids),
            "encounter_ids": list(self.encounter_ids),
            "record_counts": _record_counts(self.records),
            "records_to_change": changed,
            "confirmation_token": self.confirmation_token,
            "manifest": manifest,
        }


def _record_counts(records: Iterable[_LabRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.table] = counts.get(record.table, 0) + 1
    return dict(sorted(counts.items()))


def _query_all(query, *, lock: bool) -> list[Any]:
    if lock:
        query = query.with_for_update()
    return list(query.all())


def _one_or_none(query, *, lock: bool):
    if lock:
        query = query.with_for_update()
    return query.one_or_none()


def _require_lab_unit(db, lab_unit_id: int, label: str) -> None:
    if db.get(LabUnit, lab_unit_id) is None:
        raise RemidioLabUnitRepairError(f"{label} lab unit {lab_unit_id} was not found.")


def _append_record(records: list[_LabRecord], table: str, entity: Any) -> None:
    records.append(_LabRecord(table, int(entity.id), entity, entity.lab_unit_id))


def _encounter_matches_binding(encounter: Any, *, project_id: int, binding: Any) -> bool:
    """Match the encounter to the profile, not the project-profile mapping row."""
    return (
        encounter.project_id == project_id
        and encounter.upload_profile_id == binding.project_profile.upload_profile_id
    )


def _validate_lab_lineage(
    records: Iterable[_LabRecord], *, source_lab_unit_id: int, target_lab_unit_id: int
) -> None:
    allowed = {source_lab_unit_id, target_lab_unit_id}
    for record in records:
        if record.before_lab_unit_id not in allowed:
            raise RemidioLabUnitRepairError(
                f"Refusing mixed or unknown lineage: {record.table} {record.record_id} "
                f"has lab unit {record.before_lab_unit_id!r}; expected "
                f"{source_lab_unit_id} or {target_lab_unit_id}."
            )


def resolve_repair_scope(
    db,
    *,
    project_code: str,
    binding_id: int,
    source_lab_unit_id: int,
    target_lab_unit_id: int,
    lock: bool = False,
) -> RepairScope:
    """Resolve and validate the complete ORM lineage for one repair."""
    if source_lab_unit_id == target_lab_unit_id:
        raise RemidioLabUnitRepairError("Source and target lab units must be different.")
    if not project_code.strip():
        raise RemidioLabUnitRepairError("Project code must not be empty.")

    project = _one_or_none(
        db.query(Project).filter(Project.code == project_code), lock=lock
    )
    if project is None:
        raise RemidioLabUnitRepairError(f"Project code {project_code!r} was not found.")
    if not project.active:
        raise RemidioLabUnitRepairError(f"Project {project_code!r} is inactive.")

    _require_lab_unit(db, source_lab_unit_id, "Source")
    _require_lab_unit(db, target_lab_unit_id, "Target")

    target_boundary = _one_or_none(
        db.query(ProjectLabUnit)
        .filter(
            ProjectLabUnit.project_id == project.id,
            ProjectLabUnit.lab_unit_id == target_lab_unit_id,
            ProjectLabUnit.active.is_(True),
        ),
        lock=lock,
    )
    if target_boundary is None:
        raise RemidioLabUnitRepairError(
            f"Target lab unit {target_lab_unit_id} is not an active lab-unit boundary for project "
            f"{project_code!r}."
        )
    source_boundary = _one_or_none(
        db.query(ProjectLabUnit)
        .filter(
            ProjectLabUnit.project_id == project.id,
            ProjectLabUnit.lab_unit_id == source_lab_unit_id,
            ProjectLabUnit.active.is_(True),
        ),
        lock=lock,
    )
    if source_boundary is not None:
        raise RemidioLabUnitRepairError(
            f"Source lab unit {source_lab_unit_id} is still an active boundary for project "
            f"{project_code!r}; refusing to re-home it."
        )

    binding = _one_or_none(
        db.query(ProjectUploadProfileRemidioApiBinding)
        .join(
            ProjectUploadProfile,
            ProjectUploadProfile.id
            == ProjectUploadProfileRemidioApiBinding.project_upload_profile_id,
        )
        .filter(
            ProjectUploadProfileRemidioApiBinding.id == binding_id,
            ProjectUploadProfile.project_id == project.id,
        ),
        lock=lock,
    )
    if binding is None:
        raise RemidioLabUnitRepairError(
            f"Binding {binding_id} is not owned by project {project_code!r}."
        )
    if not binding.project_profile.active:
        raise RemidioLabUnitRepairError(
            f"Binding {binding_id} belongs to an inactive project upload profile."
        )
    if binding.lab_unit_id != target_lab_unit_id:
        raise RemidioLabUnitRepairError(
            f"Binding {binding_id} targets lab unit {binding.lab_unit_id}, not "
            f"requested target {target_lab_unit_id}."
        )
    source_rule = db.get(RemidioApiSourceRule, binding.remidio_api_source_rule_id)
    if source_rule is None or not source_rule.active:
        raise RemidioLabUnitRepairError(
            f"Binding {binding_id} has no active authoritative Remidio source rule."
        )

    links = _query_all(
        db.query(RemidioApiExamEncounter)
        .filter(RemidioApiExamEncounter.remidio_api_binding_id == binding_id)
        .order_by(RemidioApiExamEncounter.id),
        lock=lock,
    )
    if not links:
        raise RemidioLabUnitRepairError(f"Binding {binding_id} has no encounter links to repair.")

    profile_id = int(binding.project_upload_profile_id)
    encounter_ids: list[int] = []
    for link in links:
        if link.project_upload_profile_id != profile_id or link.remidio_api_binding_id != binding_id:
            raise RemidioLabUnitRepairError(
                f"Refusing link {link.id}: project/profile/binding lineage does not match the "
                "requested binding."
            )
        exam = db.get(RemidioExam, link.remidio_exam_id)
        if exam is None or exam.patient_encounter_id != link.patient_encounter_id:
            raise RemidioLabUnitRepairError(
                f"Refusing link {link.id}: Remidio exam and encounter lineage is incomplete."
            )
        encounter_ids.append(int(link.patient_encounter_id))

    if len(set(encounter_ids)) != len(encounter_ids):
        raise RemidioLabUnitRepairError("Refusing duplicate encounter lineage in binding links.")
    encounters = _query_all(
        db.query(PatientEncounters)
        .filter(PatientEncounters.id.in_(encounter_ids))
        .order_by(PatientEncounters.id),
        lock=lock,
    )
    if {int(encounter.id) for encounter in encounters} != set(encounter_ids):
        raise RemidioLabUnitRepairError("A linked encounter is missing.")
    for encounter in encounters:
        if not _encounter_matches_binding(
            encounter, project_id=project.id, binding=binding
        ):
            raise RemidioLabUnitRepairError(
                f"Refusing encounter {encounter.id}: project or upload-profile lineage does not "
                "match the binding."
            )

    records: list[_LabRecord] = []
    for encounter in encounters:
        _append_record(records, "patient_encounters", encounter)

    files = _query_all(
        db.query(EncounterFile).filter(EncounterFile.patient_encounter_id.in_(encounter_ids)).order_by(EncounterFile.id),
        lock=lock,
    )
    for row in files:
        if row.project_id != project.id:
            raise RemidioLabUnitRepairError(
                f"Refusing encounter file {row.id}: project lineage is missing or mixed."
            )
        _append_record(records, "encounter_files", row)

    pdfs = _query_all(
        db.query(EncounterFilePDF)
        .filter(EncounterFilePDF.patient_encounter_id.in_(encounter_ids))
        .order_by(EncounterFilePDF.id),
        lock=lock,
    )
    for row in pdfs:
        if row.project_id != project.id:
            raise RemidioLabUnitRepairError(
                f"Refusing encounter PDF {row.id}: project lineage is missing or mixed."
            )
        _append_record(records, "encounter_file_pdfs", row)

    images = _query_all(
        db.query(EncounterSetImage)
        .filter(EncounterSetImage.patient_encounter_id.in_(encounter_ids))
        .order_by(EncounterSetImage.id),
        lock=lock,
    )
    for row in images:
        if row.project_id != project.id:
            raise RemidioLabUnitRepairError(
                f"Refusing encounter-set image {row.id}: project lineage is missing or mixed."
            )

    image_ids = [int(row.id) for row in images]
    packages = _query_all(
        db.query(EncounterSetGradingPackage)
        .filter(EncounterSetGradingPackage.patient_encounter_id.in_(encounter_ids))
        .order_by(EncounterSetGradingPackage.id),
        lock=lock,
    )
    package_ids = [int(row.id) for row in packages]
    file_ids = [int(row.id) for row in files]
    task_conditions = [GradingTask.patient_encounter_id.in_(encounter_ids)]
    if file_ids:
        task_conditions.append(GradingTask.encounter_file_id.in_(file_ids))
    if image_ids:
        task_conditions.append(GradingTask.encounter_set_image_id.in_(image_ids))
    if package_ids:
        task_conditions.append(GradingTask.encounter_set_package_id.in_(package_ids))
    tasks = _query_all(
        db.query(GradingTask).filter(or_(*task_conditions)).order_by(GradingTask.id),
        lock=lock,
    )
    for row in tasks:
        if row.project_id != project.id:
            raise RemidioLabUnitRepairError(
                f"Refusing grading task {row.id}: project lineage is missing or mixed."
            )
        _append_record(records, "grading_tasks", row)

    task_ids = [int(row.id) for row in tasks]
    intra_conditions = []
    if file_ids:
        intra_conditions.append(IntraRaterTask.encounter_file_id.in_(file_ids))
    if task_ids:
        intra_conditions.append(IntraRaterTask.source_task_id.in_(task_ids))
    if intra_conditions:
        intra_tasks = _query_all(
            db.query(IntraRaterTask).filter(or_(*intra_conditions)).order_by(IntraRaterTask.id),
            lock=lock,
        )
        if intra_tasks:
            raise RemidioLabUnitRepairError(
                "Intra-rater derivatives exist for the repair scope. Their batch and "
                "clinical lineage require a separate reviewed repair; refusing to infer it."
            )

        regrade_tasks = _query_all(
            db.query(RegradeTask).filter(RegradeTask.source_task_id.in_(task_ids)).order_by(RegradeTask.id),
            lock=lock,
        )
    elif task_ids:
        regrade_tasks = _query_all(
            db.query(RegradeTask).filter(RegradeTask.source_task_id.in_(task_ids)).order_by(RegradeTask.id),
            lock=lock,
        )
    else:
        regrade_tasks = []
    for row in regrade_tasks:
        _append_record(records, "regrade_tasks", row)

    _validate_lab_lineage(
        records,
        source_lab_unit_id=source_lab_unit_id,
        target_lab_unit_id=target_lab_unit_id,
    )
    return RepairScope(
        project_id=int(project.id),
        project_code=project.code,
        binding_id=int(binding.id),
        project_upload_profile_id=profile_id,
        source_lab_unit_id=source_lab_unit_id,
        target_lab_unit_id=target_lab_unit_id,
        link_ids=tuple(int(link.id) for link in links),
        records=records,
    )


def preview_repair(db, **kwargs: Any) -> RepairScope:
    """Resolve a repair without changing any ORM row."""
    return resolve_repair_scope(db, lock=False, **kwargs)


def apply_repair(db, *, confirmation_token: str, **kwargs: Any) -> RepairScope:
    """Lock, re-resolve, verify, and atomically apply a repair."""
    scope = resolve_repair_scope(db, lock=True, **kwargs)
    if confirmation_token != scope.confirmation_token:
        raise RemidioLabUnitRepairError(
            "Confirmation token does not match the current resolved scope; run a fresh preview."
        )
    for record in scope.records:
        if record.before_lab_unit_id != scope.target_lab_unit_id:
            record.entity.lab_unit_id = scope.target_lab_unit_id
            db.add(record.entity)
    db.flush()
    return scope


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-code", required=True)
    parser.add_argument("--binding-id", required=True, type=int)
    parser.add_argument("--source-lab-unit-id", required=True, type=int)
    parser.add_argument("--target-lab-unit-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true", help="Persist the reviewed repair.")
    parser.add_argument("--confirm-token", help="Exact token emitted by a fresh preview.")
    parser.add_argument("--manifest", type=Path, help="Write the JSON audit manifest to this path.")
    args = parser.parse_args(argv)
    if args.apply and not args.confirm_token:
        parser.error("--apply requires --confirm-token from a fresh preview")
    if not args.apply and args.confirm_token:
        parser.error("--confirm-token is only valid with --apply")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    scope_args = {
        "project_code": args.project_code,
        "binding_id": args.binding_id,
        "source_lab_unit_id": args.source_lab_unit_id,
        "target_lab_unit_id": args.target_lab_unit_id,
    }
    try:
        with transaction_scope() as db:
            if args.apply:
                scope = apply_repair(db, confirmation_token=args.confirm_token, **scope_args)
                result = scope.to_dict(applied=True)
            else:
                scope = preview_repair(db, **scope_args)
                result = scope.to_dict()
        rendered = json.dumps(result, indent=2, sort_keys=True)
        print(rendered)
        if args.manifest:
            args.manifest.write_text(rendered + "\n", encoding="utf-8")
    except RemidioLabUnitRepairError as exc:
        print(json.dumps({"mode": "error", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
